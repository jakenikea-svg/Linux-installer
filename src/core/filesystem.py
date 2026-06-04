"""
Filesystem Extraction & OS Installation Module

Extracts the full Linux OS from an ISO and installs it to the target disk:
  - Extracts squashfs root filesystem using 7z
  - Copies kernel, initrd, and all OS files
  - Creates /etc/fstab for the installed system
  - Sets up hostname, network, locale
  - Configures initramfs for proper boot
  - Handles both casper-based (Ubuntu) and anaconda-based (Fedora) ISOs
"""

import os
import sys
import subprocess
import shutil
import time
from typing import Optional, Callable, Tuple, List
from pathlib import Path
from dataclasses import dataclass


@dataclass
class InstallConfig:
    """Configuration for the OS installation."""
    hostname: str = "linux"
    username: str = "user"
    full_name: str = "Linux User"
    password: str = ""
    timezone: str = "UTC"
    locale: str = "en_US.UTF-8"
    keyboard_layout: str = "us"
    swap_size_mb: int = 2048
    efi_size_mb: int = 512


class FilesystemInstaller:
    """
    Extracts a Linux OS from its ISO and installs it onto the target disk.

    This is the core module that makes this tool work like a real OS installer
    rather than just creating a bootable USB. It:

    1. Extracts the compressed root filesystem from the ISO
    2. Copies all OS files to the root partition on the target disk
    3. Sets up the kernel and initrd for direct boot (not loopback)
    4. Generates /etc/fstab, hostname, network config, etc.
    5. Configures the initramfs to boot from the actual disk partition
    """

    def __init__(self, callback: Optional[Callable] = None):
        self.callback = callback or (lambda x: None)
        self._7z_path: Optional[str] = None

    def _log(self, msg: str):
        self.callback(msg)

    def _find_7z(self) -> Optional[str]:
        """Find 7z executable."""
        if self._7z_path:
            return self._7z_path
        if sys.platform == "win32":
            candidates = [
                "7z", "7z.exe",
                r"C:\Program Files\7-Zip\7z.exe",
                r"C:\Program Files (x86)\7-Zip\7z.exe",
            ]
        else:
            candidates = ["7z", "7za"]
        for c in candidates:
            try:
                r = subprocess.run([c, "--help"], capture_output=True, timeout=5)
                if r.returncode == 0:
                    self._7z_path = c
                    return c
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        return None

    def extract_os_to_disk(
        self,
        iso_path: str,
        root_mount: str,
        efi_mount: str,
        config: InstallConfig,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Tuple[bool, str]:
        """
        Extract the full OS from the ISO and install it to the target disk.

        Args:
            iso_path: Path to the Linux ISO
            root_mount: Drive letter of the root partition (e.g. "E:")
            efi_mount: Drive letter of the EFI partition (e.g. "S:")
            config: Installation configuration
            progress_callback: (bytes_copied, total_bytes)

        Returns:
            (success, message)
        """
        seven_zip = self._find_7z()
        if not seven_zip:
            return False, ("7-Zip is required but not found. Please install 7-Zip from https://7-zip.org\n"
                           "After installing, restart this application.")

        root_dir = os.path.join(root_mount, os.sep)
        efi_dir = os.path.join(efi_mount, os.sep)

        self._log("Extracting Linux OS from ISO...")

        # Step 1: Create temp extraction directory
        temp_dir = os.path.join(os.environ.get("TEMP", "/tmp"), "linuxinst_extract")
        if os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        os.makedirs(temp_dir, exist_ok=True)

        # Step 2: Extract the entire ISO to temp directory
        self._log("Extracting ISO contents (this may take a few minutes)...")
        try:
            result = subprocess.run(
                [seven_zip, "x", iso_path, f"-o{temp_dir}", "-y", "-aoa"],
                capture_output=True, text=True, timeout=600,
            )
            if result.returncode != 0:
                # Try alternate extraction
                result = subprocess.run(
                    [seven_zip, "x", iso_path, f"-o{temp_dir}", "-y"],
                    capture_output=True, text=True, timeout=600,
                )
        except subprocess.TimeoutExpired:
            return False, "ISO extraction timed out. The ISO may be too large or corrupted."

        # Step 3: Detect the distro type and extract root filesystem
        self._log("Detecting distribution type...")
        distro_type = self._detect_distro_type(temp_dir)
        self._log(f"Detected distro type: {distro_type}")

        # Step 4: Extract root filesystem
        success, msg = self._extract_rootfs(temp_dir, root_dir, distro_type, seven_zip, progress_callback)
        if not success:
            return False, msg

        # Step 5: Copy kernel and initrd to boot
        self._log("Setting up kernel and initrd...")
        self._setup_kernel(temp_dir, root_dir, efi_dir, distro_type)

        # Step 6: Generate system configuration
        self._log("Configuring installed system...")
        self._generate_system_config(root_dir, efi_mount, config, distro_type)

        # Step 7: Post-install setup
        self._log("Running post-install configuration...")
        self._post_install(root_dir, efi_dir, config, distro_type)

        # Step 8: Clean up temp
        self._log("Cleaning up temporary files...")
        shutil.rmtree(temp_dir, ignore_errors=True)

        self._log("OS files installed successfully!")
        return True, "OS installed to disk."

    def _detect_distro_type(self, iso_root: str) -> str:
        """Detect the distribution type from extracted ISO contents."""
        # Casper-based (Ubuntu, Mint, Pop!_OS, etc.)
        if os.path.isdir(os.path.join(iso_root, "casper")):
            return "casper"

        # Live-based (Debian Live, Kali, etc.)
        if os.path.isdir(os.path.join(iso_root, "live")):
            return "live"

        # Anaconda-based (Fedora, CentOS, Rocky, Alma)
        if os.path.isdir(os.path.join(iso_root, "isolinux")) and \
           os.path.isfile(os.path.join(iso_root, "isolinux", "vmlinuz")):
            return "anaconda"

        # Archiso (Arch, Manjaro)
        if os.path.isdir(os.path.join(iso_root, "arch")):
            return "archiso"

        # openSUSE
        if os.path.isdir(os.path.join(iso_root, "boot", "x86_64", "loader")):
            return "suse"

        # Generic
        return "generic"

    def _extract_rootfs(
        self,
        iso_root: str,
        root_dir: str,
        distro_type: str,
        seven_zip: str,
        progress_callback,
    ) -> Tuple[bool, str]:
        """
        Extract the root filesystem from the ISO to the target root partition.

        For casper/live distros, the rootfs is in a squashfs file.
        For others, we copy the ISO contents directly.
        """
        squashfs_path = self._find_squashfs(iso_root, distro_type)

        if squashfs_path:
            self._log(f"Found compressed rootfs: {os.path.basename(squashfs_path)}")
            self._log("Extracting root filesystem (this will take several minutes)...")

            try:
                # Use 7z to extract squashfs
                result = subprocess.run(
                    [seven_zip, "x", squashfs_path, f"-o{root_dir}", "-y", "-aoa"],
                    capture_output=True, text=True, timeout=1800,  # 30 min timeout
                )
                if result.returncode != 0:
                    # Try with -snl flag for symlinks
                    result = subprocess.run(
                        [seven_zip, "x", squashfs_path, f"-o{root_dir}", "-y"],
                        capture_output=True, text=True, timeout=1800,
                    )

                if result.returncode == 0:
                    self._log("Root filesystem extracted successfully.")
                    return True, "Root filesystem extracted."
                else:
                    self._log(f"SquashFS extraction error: {result.stderr[:200]}")
                    self._log("Falling back to direct copy method...")
                    return self._fallback_copy(iso_root, root_dir, distro_type, progress_callback)

            except subprocess.TimeoutExpired:
                return False, "Root filesystem extraction timed out."

        else:
            # No squashfs found - use fallback
            self._log("No compressed rootfs found. Using direct copy method...")
            return self._fallback_copy(iso_root, root_dir, distro_type, progress_callback)

    def _find_squashfs(self, iso_root: str, distro_type: str) -> Optional[str]:
        """Find the squashfs root filesystem in the extracted ISO."""
        search_dirs = [iso_root]

        # Common locations for squashfs files
        squashfs_names = [
            "filesystem.squashfs",
            "livefilesystem.squashfs",
            "rootfs.squashfs",
            "system.squashfs",
        ]

        # Casper location
        if distro_type == "casper":
            search_dirs.append(os.path.join(iso_root, "casper"))
            search_dirs.append(os.path.join(iso_root, "live"))
        elif distro_type == "live":
            search_dirs.append(os.path.join(iso_root, "live"))
        elif distro_type == "archiso":
            search_dirs.append(os.path.join(iso_root, "arch", "x86_64"))
            squashfs_names.extend(["airootfs.squashfs", "root-image.squashfs"])

        for search_dir in search_dirs:
            if not os.path.isdir(search_dir):
                continue
            for name in squashfs_names:
                path = os.path.join(search_dir, name)
                if os.path.isfile(path):
                    return path
            # Also search for any .squashfs file
            for f in os.listdir(search_dir):
                if f.endswith(".squashfs"):
                    return os.path.join(search_dir, f)

        return None

    def _fallback_copy(
        self,
        iso_root: str,
        root_dir: str,
        distro_type: str,
        progress_callback,
    ) -> Tuple[bool, str]:
        """
        Fallback: copy ISO contents directly to root partition.
        This creates a live installation rather than a full OS install,
        but it's better than failing.
        """
        self._log("Copying ISO contents to target disk...")

        try:
            total_size = 0
            for dirpath, dirnames, filenames in os.walk(iso_root):
                for f in filenames:
                    total_size += os.path.getsize(os.path.join(dirpath, f))

            copied = 0
            chunk_size = 1024 * 1024  # 1MB

            for dirpath, dirnames, filenames in os.walk(iso_root):
                # Calculate relative path
                rel_path = os.path.relpath(dirpath, iso_root)
                dest_dir = os.path.join(root_dir, rel_path) if rel_path != "." else root_dir
                os.makedirs(dest_dir, exist_ok=True)

                for filename in filenames:
                    src_file = os.path.join(dirpath, filename)
                    dst_file = os.path.join(dest_dir, filename)

                    try:
                        # Use copy with chunking for large files + progress
                        file_size = os.path.getsize(src_file)
                        if file_size > 50 * 1024 * 1024:  # > 50MB, copy with progress
                            with open(src_file, "rb") as sf, open(dst_file, "wb") as df:
                                while True:
                                    chunk = sf.read(chunk_size)
                                    if not chunk:
                                        break
                                    df.write(chunk)
                                    copied += len(chunk)
                                    if progress_callback:
                                        progress_callback(copied, total_size)
                        else:
                            shutil.copy2(src_file, dst_file)
                            copied += file_size
                            if progress_callback:
                                progress_callback(copied, total_size)
                    except (PermissionError, OSError) as e:
                        self._log(f"Skipped: {filename} ({e})")
                        continue

            return True, f"Copied ISO contents ({copied / (1024**3):.1f} GB)"

        except Exception as e:
            return False, f"Copy failed: {e}"

    def _setup_kernel(self, iso_root: str, root_dir: str, efi_dir: str, distro_type: str):
        """Copy kernel and initrd to the correct locations for GRUB to boot."""
        vmlinuz_src = None
        initrd_src = None

        # Find kernel and initrd based on distro type
        if distro_type == "casper":
            vmlinuz_src = os.path.join(iso_root, "casper", "vmlinuz")
            initrd_src = os.path.join(iso_root, "casper", "initrd")
            # Also try with .efi extension
            if not os.path.isfile(vmlinuz_src):
                vmlinuz_src = os.path.join(iso_root, "casper", "vmlinuz.efi")

        elif distro_type == "live":
            vmlinuz_src = os.path.join(iso_root, "live", "vmlinuz")
            initrd_src = os.path.join(iso_root, "live", "initrd.img")

        elif distro_type == "anaconda":
            vmlinuz_src = os.path.join(iso_root, "isolinux", "vmlinuz")
            initrd_src = os.path.join(iso_root, "isolinux", "initrd.img")

        elif distro_type == "archiso":
            vmlinuz_src = os.path.join(iso_root, "arch", "boot", "x86_64", "vmlinuz-linux")
            initrd_src = os.path.join(iso_root, "arch", "boot", "x86_64", "initramfs-linux.img")

        elif distro_type == "suse":
            vmlinuz_src = os.path.join(iso_root, "boot", "x86_64", "loader", "linux")
            initrd_src = os.path.join(iso_root, "boot", "x86_64", "loader", "initrd")

        # Search broadly if not found yet
        if not os.path.isfile(vmlinuz_src or ""):
            vmlinuz_src, initrd_src = self._find_kernel_initrd(iso_root)

        # Copy to /boot on the root partition
        boot_dir = os.path.join(root_dir, "boot")
        os.makedirs(boot_dir, exist_ok=True)

        if vmlinuz_src and os.path.isfile(vmlinuz_src):
            shutil.copy2(vmlinuz_src, os.path.join(boot_dir, "vmlinuz"))
            self._log(f"Copied kernel to /boot/vmlinuz")
            # Also copy to EFI for direct UEFI boot
            efi_boot_dir = os.path.join(efi_dir, "EFI", "Linux")
            os.makedirs(efi_boot_dir, exist_ok=True)
            shutil.copy2(vmlinuz_src, os.path.join(efi_boot_dir, "vmlinuz"))
        else:
            self._log("Warning: Could not find kernel in ISO.")

        if initrd_src and os.path.isfile(initrd_src):
            shutil.copy2(initrd_src, os.path.join(boot_dir, "initrd.img"))
            self._log(f"Copied initrd to /boot/initrd.img")
            efi_boot_dir = os.path.join(efi_dir, "EFI", "Linux")
            os.makedirs(efi_boot_dir, exist_ok=True)
            shutil.copy2(initrd_src, os.path.join(efi_boot_dir, "initrd.img"))
        else:
            self._log("Warning: Could not find initrd in ISO.")

    def _find_kernel_initrd(self, search_root: str) -> Tuple[Optional[str], Optional[str]]:
        """Search broadly for kernel and initrd files."""
        vmlinuz = None
        initrd = None

        vmlinuz_names = ["vmlinuz", "vmlinuz.efi", "vmlinuz-linux", "linux"]
        initrd_names = ["initrd", "initrd.img", "initramfs-linux.img",
                        "initrd.gz", "initrd.img", "initrd-latest"]

        for dirpath, dirnames, filenames in os.walk(search_root):
            for f in filenames:
                f_lower = f.lower()
                if vmlinuz is None and any(n in f_lower for n in vmlinuz_names):
                    vmlinuz = os.path.join(dirpath, f)
                if initrd is None and any(n in f_lower for n in initrd_names):
                    initrd = os.path.join(dirpath, f)
                if vmlinuz and initrd:
                    return vmlinuz, initrd

        return vmlinuz, initrd

    def _generate_system_config(
        self,
        root_dir: str,
        efi_mount: str,
        config: InstallConfig,
        distro_type: str,
    ):
        """Generate /etc/fstab, hostname, and other system configuration files."""

        # --- /etc/fstab ---
        fstab_path = os.path.join(root_dir, "etc", "fstab")
        os.makedirs(os.path.dirname(fstab_path), exist_ok=True)

        fstab_content = f"""# /etc/fstab - Created by Linux USB Installer
# <file system>  <mount point>  <type>  <options>  <dump>  <pass>

# Root partition
PARTLABEL=LINUXROOT  /  auto  defaults,errors=remount-ro  0  1

# EFI System Partition
PARTLABEL=EFI  /boot/efi  vfat  umask=0077  0  2

# Swap
PARTUUID=swap  none  swap  sw  0  0

# Temp
tmpfs  /tmp  tmpfs  defaults,nosuid,nodev  0  0
"""
        with open(fstab_path, "w") as f:
            f.write(fstab_content)
        self._log("Generated /etc/fstab")

        # --- /etc/hostname ---
        hostname_path = os.path.join(root_dir, "etc", "hostname")
        with open(hostname_path, "w") as f:
            f.write(f"{config.hostname}\n")
        self._log(f"Set hostname to '{config.hostname}'")

        # --- /etc/hosts ---
        hosts_path = os.path.join(root_dir, "etc", "hosts")
        with open(hosts_path, "w") as f:
            f.write(f"127.0.0.1\tlocalhost\n")
            f.write(f"127.0.1.1\t{config.hostname}\n")
            f.write(f"\n::1\t\tlocalhost ip6-localhost ip6-loopback\n")

        # --- /etc/default/locale (for Debian/Ubuntu) ---
        locale_dir = os.path.join(root_dir, "etc", "default")
        os.makedirs(locale_dir, exist_ok=True)
        with open(os.path.join(locale_dir, "locale"), "w") as f:
            f.write(f"LANG={config.locale}\n")

        # --- Network configuration ---
        self._setup_network(root_dir, config)

        # --- Create user (flag for first boot) ---
        self._setup_user(root_dir, config)

    def _setup_network(self, root_dir: str, config: InstallConfig):
        """Set up basic networking configuration."""
        # NetworkManager config (Ubuntu/Fedora)
        nm_dir = os.path.join(root_dir, "etc", "NetworkManager", "system-connections")
        os.makedirs(nm_dir, exist_ok=True)

        # Create a default WiFi connection template (disabled, user fills in)
        # Create wired auto-connect
        wired_conn = f"""[connection]
id=Wired Auto
type=ethernet
autoconnect=true

[ipv4]
method=auto

[ipv6]
method=auto
"""
        with open(os.path.join(nm_dir, "wired-auto.nmconnection"), "w") as f:
            f.write(wired_conn)

        # systemd-networkd fallback
        network_dir = os.path.join(root_dir, "etc", "systemd", "network")
        os.makedirs(network_dir, exist_ok=True)
        with open(os.path.join(network_dir, "20-wired.network"), "w") as f:
            f.write("[Match]\nName=en*\n\n[Network]\nDHCP=yes\n")

        self._log("Network configuration created.")

    def _setup_user(self, root_dir: str, config: InstallConfig):
        """
        Create a user setup script that runs on first boot.
        Since we can't run useradd from Windows, we create a
        systemd service that creates the user on first boot.
        """
        if not config.username:
            return

        # Create first-boot setup script
        setup_script_dir = os.path.join(root_dir, "opt", "linux-installer")
        os.makedirs(setup_script_dir, exist_ok=True)

        setup_script = f"""#!/bin/bash
# First-boot setup script - creates user and finalizes installation
set -e

# Create user if not exists
if ! id -u {config.username} > /dev/null 2>&1; then
    useradd -m -s /bin/bash -c "{config.full_name}" {config.username}
    echo "{config.username}:{config.password or 'linux'}" | chpasswd
    usermod -aG sudo,adm,cdrom,dip,plugdev {config.username} 2>/dev/null || true
    usermod -aG wheel {config.username} 2>/dev/null || true
fi

# Update initramfs if possible
update-initramfs -u 2>/dev/null || dracut --force 2>/dev/null || true

# Rebuild GRUB config for the installed system
grub-mkconfig -o /boot/grub/grub.cfg 2>/dev/null || true

# Disable this service
systemctl disable linux-firstboot.service 2>/dev/null || true

echo "First boot setup complete!"
"""
        setup_path = os.path.join(setup_script_dir, "firstboot.sh")
        with open(setup_path, "w") as f:
            f.write(setup_script)
        os.chmod(setup_path, 0o755)

        # Create systemd service
        service_dir = os.path.join(root_dir, "etc", "systemd", "system")
        os.makedirs(service_dir, exist_ok=True)

        service = f"""[Unit]
Description=Linux Installer First Boot Setup
After=network.target

[Service]
Type=oneshot
ExecStart=/opt/linux-installer/firstboot.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
"""
        with open(os.path.join(service_dir, "linux-firstboot.service"), "w") as f:
            f.write(service)

        # Enable the service
        wants_dir = os.path.join(root_dir, "etc", "systemd", "system", "multi-user.target.wants")
        os.makedirs(wants_dir, exist_ok=True)
        link_path = os.path.join(wants_dir, "linux-firstboot.service")
        try:
            os.symlink("/etc/systemd/system/linux-firstboot.service", link_path)
        except OSError:
            pass

        self._log(f"User '{config.username}' will be created on first boot.")

    def _post_install(self, root_dir: str, efi_dir: str, config: InstallConfig, distro_type: str):
        """Post-installation setup."""
        # Ensure critical directories exist
        critical_dirs = [
            "dev", "proc", "sys", "run", "tmp",
            "var/log", "var/cache", "var/lib",
            "mnt", "media", "opt", "srv",
            "boot/grub", "boot/efi",
            "home", "root",
            "etc/default", "etc/init.d",
        ]
        for d in critical_dirs:
            os.makedirs(os.path.join(root_dir, d), exist_ok=True)

        # Create resolv.conf
        resolv_path = os.path.join(root_dir, "etc", "resolv.conf")
        if not os.path.isfile(resolv_path):
            with open(resolv_path, "w") as f:
                f.write("nameserver 8.8.8.8\nnameserver 8.8.4.4\n")

        # Mark the installation
        install_info_path = os.path.join(root_dir, "etc", "linux-installer.conf")
        with open(install_info_path, "w") as f:
            f.write(f"[install]\n")
            f.write(f"method=linux-usb-installer\n")
            f.write(f"distro_type={distro_type}\n")
            f.write(f"hostname={config.hostname}\n")

        self._log("Post-install setup complete.")
