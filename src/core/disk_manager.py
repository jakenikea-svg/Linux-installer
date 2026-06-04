"""
Disk & Media Detection Module

Detects ALL writable media: USB flash drives, external HDDs, SD cards,
memory sticks, etc. Provides diskpart scripts for partitioning any target
device with a proper Linux installation layout.
"""

import os
import sys
import subprocess
import ctypes
import psutil
from dataclasses import dataclass
from typing import List, Optional, Callable, Tuple


@dataclass
class DiskDevice:
    """Represents any writable disk device."""
    index: int                    # Windows disk index
    device_id: str                # \\.\PhysicalDriveN
    drive_letter: str             # e.g. "E:" (first partition)
    label: str                    # Volume label
    size_bytes: int               # Total size in bytes
    model: str                    # Drive model
    vendor: str                   # Manufacturer
    media_type: str               # "USB Flash", "USB HDD", "SD Card", "External HDD"
    bus_type: str                 # USB, SD, SATA, NVMe
    filesystem: str               # Current filesystem
    partition_style: str          # "GPT" or "MBR"
    is_removable: bool            # Removable media flag

    @property
    def size_gb(self) -> float:
        return self.size_bytes / (1024 ** 3)

    @property
    def display_name(self) -> str:
        size_str = f"{self.size_gb:.1f} GB"
        label_part = f" ({self.label})" if self.label else ""
        model_part = f" - {self.model}" if self.model else ""
        type_icon = {"USB Flash": "[USB]", "USB HDD": "[Ext HDD]",
                     "SD Card": "[SD]", "External HDD": "[Ext HDD]",
                     "Internal": "[HDD]"}.get(self.media_type, "[Disk]")
        return f"{type_icon} {self.drive_letter}{label_part} [{size_str}]{model_part}"


class DiskDetector:
    """Detects all writable disk devices on Windows."""

    def detect_all(self) -> List[DiskDevice]:
        """Detect all disks that can be written to (USB, HDD, SD card, etc.)."""
        devices = []

        if sys.platform == "win32":
            try:
                devices = self._detect_windows()
            except Exception:
                devices = self._detect_fallback()
        else:
            devices = self._detect_linux()

        return devices

    def _detect_windows(self) -> List[DiskDevice]:
        """Detect all disks on Windows using WMI."""
        try:
            import wmi
            c = wmi.WMI()
            devices = []

            for disk in c.Win32_DiskDrive():
                index = int(disk.Index)
                device_id = disk.DeviceID
                size = int(disk.Size) if disk.Size else 0
                model = (disk.Model or "").strip()
                vendor = (disk.Manufacturer or "").strip()

                # Determine media type and bus
                media_type = self._classify_media(disk)
                bus_type = disk.InterfaceType or "Unknown"
                is_removable = False

                if disk.MediaType and "removable" in disk.MediaType.lower():
                    is_removable = True
                if disk.PNPDeviceID and "USB" in disk.PNPDeviceID.upper():
                    bus_type = "USB"
                    is_removable = True
                if disk.PNPDeviceID and "SD" in disk.PNPDeviceID.upper():
                    bus_type = "SD"
                    is_removable = True

                # Get drive letters
                drive_letters = self._get_drive_letters(c, index)
                drive_letter = drive_letters[0] if drive_letters else ""

                # Get volume info
                fs, label = "", ""
                if drive_letter:
                    for vol in c.Win32_LogicalDisk(DeviceID=drive_letter):
                        fs = vol.FileSystem or ""
                        label = vol.VolumeName or ""
                        break

                # Determine partition style
                partition_style = "GPT" if "GPT" in (disk.PartitionStyle or "") else "MBR"

                dev = DiskDevice(
                    index=index,
                    device_id=device_id,
                    drive_letter=drive_letter,
                    label=label,
                    size_bytes=size,
                    model=model,
                    vendor=vendor,
                    media_type=media_type,
                    bus_type=bus_type,
                    filesystem=fs,
                    partition_style=partition_style,
                    is_removable=is_removable,
                )
                devices.append(dev)

            return devices

        except ImportError:
            return self._detect_fallback()

    def _classify_media(self, disk) -> str:
        """Classify the media type based on disk properties."""
        model_lower = (disk.Model or "").lower()
        pnp = (disk.PNPDeviceID or "").upper()
        media = (disk.MediaType or "").lower()
        interface = (disk.InterfaceType or "").upper()
        size_gb = (int(disk.Size) if disk.Size else 0) / (1024**3)

        # SD Card detection
        if "SD" in pnp or "SDCARD" in pnp or "MMC" in pnp:
            return "SD Card"

        # USB detection
        if "USB" in pnp:
            if size_gb < 256:
                return "USB Flash"
            else:
                return "USB HDD"

        # Removable media
        if "removable" in media:
            return "USB Flash"

        # External vs Internal
        if interface == "USB":
            return "USB HDD"

        if "EXTERNAL" in model_lower or "EXPANSION" in model_lower or "ELEMENTS" in model_lower:
            return "External HDD"

        return "Internal"

    def _get_drive_letters(self, wmi_conn, disk_index: int) -> List[str]:
        """Map disk index to drive letters."""
        letters = []
        try:
            for partition in wmi_conn.Win32_DiskPartition():
                if partition.DiskIndex == disk_index:
                    for logical in wmi_conn.Win32_LogicalDiskToPartition():
                        ant = str(logical.Antecedent)
                        dep = str(logical.Dependent)
                        if partition.DeviceID in ant:
                            # Extract drive letter from Dependent
                            for part in dep.split('"'):
                                if len(part) == 2 and part[1] == ":":
                                    letters.append(part)
                                    break
        except Exception:
            pass
        return letters

    def _detect_fallback(self) -> List[DiskDevice]:
        """Fallback using psutil."""
        devices = []
        for partition in psutil.disk_partitions(all=True):
            try:
                usage = psutil.disk_usage(partition.mountpoint)
            except (PermissionError, FileNotFoundError):
                continue

            dev = DiskDevice(
                index=0,
                device_id=partition.device,
                drive_letter=partition.mountpoint.rstrip("\\"),
                label="",
                size_bytes=usage.total,
                model="Disk",
                vendor="",
                media_type="External",
                bus_type="Unknown",
                filesystem=partition.fstype,
                partition_style="MBR",
                is_removable=True,
            )
            devices.append(dev)
        return devices

    def _detect_linux(self) -> List[DiskDevice]:
        """Detect disks on Linux (dev/testing)."""
        devices = []
        for partition in psutil.disk_partitions(all=True):
            try:
                usage = psutil.disk_usage(partition.mountpoint)
            except (PermissionError, FileNotFoundError):
                continue

            dev = DiskDevice(
                index=0,
                device_id=partition.device,
                drive_letter=partition.mountpoint,
                label=os.path.basename(partition.mountpoint),
                size_bytes=usage.total,
                model="Disk",
                vendor="",
                media_type="External",
                bus_type="USB",
                filesystem=partition.fstype,
                partition_style="MBR",
                is_removable=True,
            )
            devices.append(dev)
        return devices


class DiskFormatter:
    """
    Partitions and formats a target disk for Linux installation.

    Layout for UEFI systems (GPT):
      - Partition 1: EFI System Partition (FAT32, 512MB)
      - Partition 2: swap (optional, 2GB)
      - Partition 3: Root filesystem (ext4, rest of disk)

    Layout for BIOS systems (MBR):
      - Partition 1: /boot (ext2, 512MB) — GRUB goes here
      - Partition 2: swap (optional, 2GB)
      - Partition 3: Root filesystem (ext4, rest of disk)

    Layout for Hybrid (GPT with BIOS boot):
      - Partition 1: EFI System Partition (FAT32, 512MB)
      - Partition 2: BIOS Boot Partition (1MB, no FS)
      - Partition 3: swap (optional, 2GB)
      - Partition 4: Root filesystem (ext4, rest of disk)
    """

    @staticmethod
    def create_diskpart_script_uefi(disk_index: int, efi_mb: int = 512, swap_mb: int = 2048) -> str:
        """GPT layout for UEFI boot."""
        return f"""select disk {disk_index}
clean
convert gpt
create partition efi size={efi_mb}
format fs=fat32 quick label="EFI"
assign letter=S
create partition primary size={swap_mb}
set id=0657FD6D-A4AB-43C4-84E5-0933C84B4F4F
create partition primary
format fs=ntfs quick label="LINUXROOT"
assign
exit
"""

    @staticmethod
    def create_diskpart_script_bios(disk_index: int, boot_mb: int = 512, swap_mb: int = 2048) -> str:
        """MBR layout for BIOS boot."""
        return f"""select disk {disk_index}
clean
convert mbr
create partition primary size={boot_mb}
format fs=fat32 quick label="BOOT"
active
assign letter=S
create partition primary size={swap_mb}
create partition primary
format fs=ntfs quick label="LINUXROOT"
assign
exit
"""

    @staticmethod
    def create_diskpart_script_hybrid(disk_index: int, efi_mb: int = 512, swap_mb: int = 2048) -> str:
        """Hybrid GPT layout for both UEFI and BIOS boot."""
        return f"""select disk {disk_index}
clean
convert gpt
create partition efi size={efi_mb}
format fs=fat32 quick label="EFI"
assign letter=S
create partition primary size=16
set id=21686148-6449-6E6F-744E-656564454649
create partition primary size={swap_mb}
set id=0657FD6D-A4AB-43C4-84E5-0933C84B4F4F
create partition primary
format fs=ntfs quick label="LINUXROOT"
assign
exit
"""

    @staticmethod
    def run_diskpart(script: str, callback: Optional[Callable] = None) -> Tuple[bool, str]:
        """Execute a diskpart script (requires admin)."""
        script_path = os.path.join(os.environ.get("TEMP", "/tmp"), "linuxinst_diskpart.txt")
        with open(script_path, "w") as f:
            f.write(script)

        try:
            if callback:
                callback("Partitioning disk...")
            result = subprocess.run(
                ["diskpart", "/s", script_path],
                capture_output=True, text=True, timeout=120, shell=True,
            )
            try:
                os.remove(script_path)
            except OSError:
                pass

            success = result.returncode == 0
            output = result.stdout + result.stderr
            if callback:
                callback("Partitioning complete." if success else f"Partitioning failed: {output[:200]}")
            return success, output

        except subprocess.TimeoutExpired:
            return False, "Diskpart timed out."
        except Exception as e:
            return False, str(e)

    @staticmethod
    def is_admin() -> bool:
        """Check admin privileges."""
        try:
            if sys.platform == "win32":
                return ctypes.windll.shell32.IsUserAnAdmin() != 0
            return os.geteuid() == 0
        except Exception:
            return False

    @staticmethod
    def relaunch_as_admin():
        """UAC elevation."""
        if sys.platform != "win32":
            return
        try:
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, " ".join(sys.argv), None, 1
            )
            sys.exit(0)
        except Exception:
            pass
