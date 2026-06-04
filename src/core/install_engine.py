"""
Installation Engine - Orchestrates the Full OS Installation

This is the brain of the installer. It coordinates:
1. Partition the target disk
2. Install GRUB bootloader
3. Extract and install the OS from the ISO
4. Configure the installed system (fstab, hostname, user, etc.)
5. Verify and finalize

The result is a fully installed Linux system on the target media
that boots via GRUB — just like installing from a DVD, but to a USB/HDD/SD card.
"""

import os
import sys
import time
from typing import Optional, Callable, Tuple
from enum import Enum

from .disk_manager import DiskDevice, DiskFormatter
from .filesystem import FilesystemInstaller, InstallConfig
from .grub_installer import GrubInstaller
from .iso_handler import ISOHandler, ISOInfo


class InstallPhase(Enum):
    INITIALIZING = "Initializing"
    PARTITIONING = "Partitioning disk"
    INSTALLING_GRUB = "Installing GRUB bootloader"
    EXTRACTING_OS = "Extracting and installing Linux"
    CONFIGURING = "Configuring system"
    VERIFYING = "Verifying installation"
    COMPLETE = "Installation complete"
    FAILED = "Installation failed"


class InstallEngine:
    """
    Main installation engine. Orchestrates installing a Linux OS
    from an ISO onto a target disk (USB, HDD, SD card, etc.).
    """

    def __init__(
        self,
        iso_path: str,
        target_disk: DiskDevice,
        boot_mode: str = "hybrid",
        install_config: Optional[InstallConfig] = None,
        callback: Optional[Callable[[InstallPhase, float, str], None]] = None,
    ):
        self.iso_path = iso_path
        self.target_disk = target_disk
        self.boot_mode = boot_mode
        self.install_config = install_config or InstallConfig()
        self.callback = callback or (lambda p, pr, m: None)

        self.iso_handler = ISOHandler(callback=self._log)
        self.fs_installer = FilesystemInstaller(callback=self._log)
        self.iso_info: Optional[ISOInfo] = None
        self._phase = InstallPhase.INITIALIZING
        self._progress = 0.0
        self._cancelled = False
        self._efi_letter = "S:"
        self._data_letter = ""

    def _log(self, msg: str):
        self.callback(self._phase, self._progress, msg)

    def _update(self, phase: InstallPhase, progress: float, msg: str = ""):
        self._phase = phase
        self._progress = progress
        self.callback(phase, progress, msg)

    def cancel(self):
        self._cancelled = True

    def run(self) -> Tuple[bool, str]:
        """Execute the full installation."""
        try:
            # 1. Validate
            self._update(InstallPhase.INITIALIZING, 0.0, "Validating inputs...")
            ok, msg = self._validate()
            if not ok:
                self._update(InstallPhase.FAILED, 0.0, msg)
                return False, msg

            # 2. Partition
            self._update(InstallPhase.PARTITIONING, 0.05, "Partitioning target disk...")
            ok, msg = self._partition()
            if not ok:
                self._update(InstallPhase.FAILED, 0.1, msg)
                return False, msg

            # 3. Install GRUB
            self._update(InstallPhase.INSTALLING_GRUB, 0.15, "Installing GRUB bootloader...")
            ok, msg = self._install_grub()
            if not ok:
                self._update(InstallPhase.FAILED, 0.2, msg)
                return False, msg

            # 4. Extract and install OS
            self._update(InstallPhase.EXTRACTING_OS, 0.25, "Extracting Linux OS from ISO...")
            ok, msg = self._extract_os()
            if not ok:
                self._update(InstallPhase.FAILED, 0.7, msg)
                return False, msg

            # 5. Configure system
            self._update(InstallPhase.CONFIGURING, 0.85, "Configuring installed system...")
            ok, msg = self._configure()
            if not ok:
                self._update(InstallPhase.FAILED, 0.9, msg)
                return False, msg

            # 6. Verify
            self._update(InstallPhase.VERIFYING, 0.95, "Verifying installation...")
            ok, msg = self._verify()
            if not ok:
                self._log(f"Warning: {msg}")

            self._update(InstallPhase.COMPLETE, 1.0, "Linux installed successfully!")
            return True, "Installation complete."

        except Exception as e:
            self._update(InstallPhase.FAILED, self._progress, f"Error: {e}")
            return False, str(e)

    def _validate(self) -> Tuple[bool, str]:
        """Validate inputs."""
        if not DiskFormatter.is_admin():
            return False, "Administrator privileges required. Right-click → Run as administrator."

        ok, msg = self.iso_handler.validate_iso(self.iso_path)
        if not ok:
            return False, msg

        self.iso_info = self.iso_handler.analyze_iso(self.iso_path)
        self._log(f"Detected: {self.iso_info.display_name} ({self.iso_info.size_gb:.1f} GB)")
        self._log(f"Type: {self.iso_info.distro_type} | EFI: {self.iso_info.has_efi} | BIOS: {self.iso_info.has_bios}")

        if self.iso_info.size_bytes > self.target_disk.size_bytes * 0.9:
            return False, (f"ISO ({self.iso_info.size_gb:.1f} GB) is too large for "
                           f"target disk ({self.target_disk.size_gb:.1f} GB).")

        if self.target_disk.size_bytes < 2 * 1024**3:
            return False, "Target disk must be at least 2 GB."

        # Check for 7-Zip
        if not self.fs_installer._find_7z():
            return False, ("7-Zip is required. Install it from https://7-zip.org\n"
                           "After installing 7-Zip, restart this application.")

        return True, "Validation passed."

    def _partition(self) -> Tuple[bool, str]:
        """Partition and format the target disk."""
        self._log(f"Partitioning {self.target_disk.model or 'disk'} (Disk {self.target_disk.index})...")
        self._log("WARNING: All data on this disk will be erased!")

        if self.boot_mode == "uefi":
            script = DiskFormatter.create_diskpart_script_uefi(self.target_disk.index)
        elif self.boot_mode == "bios":
            script = DiskFormatter.create_diskpart_script_bios(self.target_disk.index)
        else:
            script = DiskFormatter.create_diskpart_script_hybrid(self.target_disk.index)

        ok, output = DiskFormatter.run_diskpart(script, callback=self._log)

        if ok:
            time.sleep(3)  # Wait for Windows to recognize partitions
            self._detect_partition_letters()
            self._log(f"EFI partition: {self._efi_letter} | Root partition: {self._data_letter}")
        else:
            return False, f"Partitioning failed: {output[:300]}"

        return True, "Disk partitioned."

    def _detect_partition_letters(self):
        """Detect drive letters after partitioning."""
        import psutil

        if os.path.isdir("S:\\"):
            self._efi_letter = "S:"

        # Find the LINUXROOT partition
        for part in psutil.disk_partitions(all=True):
            try:
                mount = part.mountpoint.rstrip("\\")
                if mount == self._efi_letter:
                    continue
                # Check if it's our LINUXROOT
                if self._is_linuxroot(mount):
                    self._data_letter = mount
            except Exception:
                continue

        # Fallback: look for empty NTFS volumes
        if not self._data_letter:
            for letter in "EFGHIJKLMNOPQRSTUVWXYZ":
                drive = f"{letter}:"
                if os.path.isdir(drive + "\\") and drive != self._efi_letter:
                    try:
                        if len(os.listdir(drive + "\\")) == 0:
                            self._data_letter = drive
                            break
                    except Exception:
                        continue

    def _is_linuxroot(self, mount: str) -> bool:
        """Check if a partition is our LINUXROOT."""
        if sys.platform != "win32":
            return False
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(1024)
            ctypes.windll.kernel32.GetVolumeInformationW(
                mount, buf, 1024, None, None, None, None, 0
            )
            return buf.value.upper() == "LINUXROOT"
        except Exception:
            return False

    def _install_grub(self) -> Tuple[bool, str]:
        """Install GRUB bootloader."""
        grub = GrubInstaller(
            efi_mount=self._efi_letter,
            root_mount=self._data_letter,
            boot_mode=self.boot_mode,
            distro_type=self.iso_info.distro_type if self.iso_info else "generic",
            callback=self._log,
        )
        return grub.install()

    def _extract_os(self) -> Tuple[bool, str]:
        """Extract the OS from ISO and install to disk."""
        def progress_cb(copied, total):
            frac = copied / total if total > 0 else 0
            self._progress = 0.25 + frac * 0.55  # 25% to 80%
            gb_copied = copied / (1024**3)
            gb_total = total / (1024**3)
            self.callback(self._phase, self._progress,
                          f"Installing: {gb_copied:.1f} / {gb_total:.1f} GB ({frac*100:.0f}%)")

        return self.fs_installer.extract_os_to_disk(
            iso_path=self.iso_path,
            root_mount=self._data_letter,
            efi_mount=self._efi_letter,
            config=self.install_config,
            progress_callback=progress_cb,
        )

    def _configure(self) -> Tuple[bool, str]:
        """Final configuration (already done during extraction)."""
        # Write a README to the root partition
        readme = os.path.join(self._data_letter, "README.txt")
        try:
            with open(readme, "w") as f:
                f.write(f"Linux Installation\n{'='*40}\n\n")
                f.write(f"Distribution: {self.iso_info.display_name if self.iso_info else 'Linux'}\n")
                f.write(f"Boot Mode: {self.boot_mode}\n")
                f.write(f"Hostname: {self.install_config.hostname}\n")
                f.write(f"Installed by: Linux USB Installer\n\n")
                f.write(f"To boot:\n")
                f.write(f"1. Restart computer with this drive connected\n")
                f.write(f"2. Press boot menu key (F12/F8/Esc)\n")
                f.write(f"3. Select this drive\n")
                f.write(f"4. On first boot, user will be created automatically\n")
        except Exception:
            pass

        return True, "Configuration complete."

    def _verify(self) -> Tuple[bool, str]:
        """Verify the installation."""
        issues = []

        # Check EFI partition
        efi_boot = os.path.join(self._efi_letter, "EFI", "Boot")
        if not os.path.isdir(efi_boot):
            issues.append("EFI Boot directory missing")
        else:
            efi_files = os.listdir(efi_boot)
            if not any(f.upper().endswith(".EFI") for f in efi_files):
                issues.append("No .EFI boot file found")

        # Check grub.cfg
        if not os.path.isfile(os.path.join(self._efi_letter, "grub", "grub.cfg")):
            issues.append("grub.cfg not found on EFI partition")

        # Check root partition has OS files
        if self._data_letter:
            root = os.path.join(self._data_letter, os.sep)
            if not os.path.isdir(os.path.join(root, "etc")):
                issues.append("/etc directory not found on root partition")
            if not os.path.isdir(os.path.join(root, "boot")):
                issues.append("/boot directory not found on root partition")
            if not os.path.isfile(os.path.join(root, "boot", "vmlinuz")):
                issues.append("Kernel not found at /boot/vmlinuz")

        if issues:
            return False, "; ".join(issues)
        return True, "Installation verified."
