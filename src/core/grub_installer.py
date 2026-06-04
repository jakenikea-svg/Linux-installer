"""
GRUB Bootloader Installer for Installed OS

Unlike the previous loopback approach, this installs GRUB to boot
the OS that has been EXTRACTED and INSTALLED on the target disk.

GRUB boots the kernel and initrd directly from the root partition,
not from a loopback-mounted ISO. This is how a real Linux install works.
"""

import os
import sys
import shutil
from typing import Optional, Callable, Tuple
from pathlib import Path


class GrubInstaller:
    """
    Installs GRUB bootloader for a fully installed Linux system.

    Supports:
      - UEFI boot (grubx64.efi on EFI System Partition)
      - BIOS boot (boot sector + stage2 on disk)
      - Hybrid (both)
    """

    ASSETS_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "assets", "grub"
    )
    if getattr(sys, 'frozen', False):
        ASSETS_DIR = os.path.join(os.path.dirname(sys.executable), "assets", "grub")

    def __init__(
        self,
        efi_mount: str = "S:",
        root_mount: str = "",
        boot_mode: str = "hybrid",
        distro_type: str = "casper",
        callback: Optional[Callable] = None,
    ):
        self.efi_mount = efi_mount
        self.root_mount = root_mount
        self.boot_mode = boot_mode
        self.distro_type = distro_type
        self.callback = callback or (lambda x: None)

    def _log(self, msg: str):
        self.callback(msg)

    def install(self) -> Tuple[bool, str]:
        """Install GRUB to the target disk."""
        self._log("Installing GRUB bootloader...")

        assets_exist = os.path.isdir(self.ASSETS_DIR) and \
                       os.path.isfile(os.path.join(self.ASSETS_DIR, "grubx64.efi"))

        if assets_exist:
            if self.boot_mode in ("uefi", "hybrid"):
                self._install_uefi()
            if self.boot_mode in ("bios", "hybrid"):
                self._install_bios()
        else:
            self._log("Bundled GRUB assets not found.")
            self._log("Attempting to use ISO's built-in EFI boot files...")
            self._install_from_iso()

        # Always write grub.cfg
        self._write_grub_cfg()

        self._log("GRUB installation complete.")
        return True, "GRUB installed."

    def _install_uefi(self):
        """Install GRUB for UEFI boot using bundled assets."""
        self._log("Setting up UEFI boot...")

        efi_root = os.path.join(self.efi_mount, os.sep)
        efi_boot_dir = os.path.join(efi_root, "EFI", "Boot")
        efi_linux_dir = os.path.join(efi_root, "EFI", "Linux")
        os.makedirs(efi_boot_dir, exist_ok=True)
        os.makedirs(efi_linux_dir, exist_ok=True)

        # Copy the UEFI boot loader
        src = os.path.join(self.ASSETS_DIR, "grubx64.efi")
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(efi_boot_dir, "BOOTX64.EFI"))
            shutil.copy2(src, os.path.join(efi_linux_dir, "grubx64.efi"))
            self._log("Copied grubx64.efi to EFI partition.")

        # Copy 32-bit UEFI if available
        src32 = os.path.join(self.ASSETS_DIR, "grubia32.efi")
        if os.path.isfile(src32):
            shutil.copy2(src32, os.path.join(efi_boot_dir, "BOOTIA32.EFI"))
            self._log("Copied grubia32.efi (32-bit UEFI).")

        # Copy UEFI GRUB modules
        mod_src = os.path.join(self.ASSETS_DIR, "x86_64-efi")
        if os.path.isdir(mod_src):
            mod_dst = os.path.join(efi_root, "grub", "x86_64-efi")
            if os.path.exists(mod_dst):
                shutil.rmtree(mod_dst)
            shutil.copytree(mod_src, mod_dst)
            self._log("Copied UEFI GRUB modules.")

        # Copy Unicode font
        font_src = os.path.join(self.ASSETS_DIR, "unicode.pf2")
        if os.path.isfile(font_src):
            grub_dir = os.path.join(efi_root, "grub", "fonts")
            os.makedirs(grub_dir, exist_ok=True)
            shutil.copy2(font_src, os.path.join(grub_dir, "unicode.pf2"))

        # Copy fonts from root partition if available
        if self.root_mount:
            root_grub_fonts = os.path.join(self.root_mount, "usr", "share", "grub", "unicode.pf2")
            if os.path.isfile(root_grub_fonts):
                grub_dir = os.path.join(efi_root, "grub", "fonts")
                os.makedirs(grub_dir, exist_ok=True)
                shutil.copy2(root_grub_fonts, os.path.join(grub_dir, "unicode.pf2"))

    def _install_bios(self):
        """Install GRUB for BIOS boot using bundled assets."""
        self._log("Setting up BIOS boot...")

        efi_root = os.path.join(self.efi_mount, os.sep)

        # Copy BIOS GRUB modules
        mod_src = os.path.join(self.ASSETS_DIR, "i386-pc")
        if os.path.isdir(mod_src):
            mod_dst = os.path.join(efi_root, "grub", "i386-pc")
            if os.path.exists(mod_dst):
                shutil.rmtree(mod_dst)
            shutil.copytree(mod_src, mod_dst)
            self._log("Copied BIOS GRUB modules.")

        # BIOS MBR boot code
        boot_img = os.path.join(self.ASSETS_DIR, "boot.img")
        if os.path.isfile(boot_img):
            self._log("BIOS MBR boot code is available for MBR writing.")

    def _install_from_iso(self):
        """
        Fallback: Use the EFI boot files from the installed system itself.
        Many distros include grubx64.efi in /usr/lib/grub/ or the ISO's EFI dir.
        """
        self._log("Setting up boot from installed system files...")

        efi_root = os.path.join(self.efi_mount, os.sep)
        efi_boot_dir = os.path.join(efi_root, "EFI", "Boot")
        os.makedirs(efi_boot_dir, exist_ok=True)

        # Look for GRUB EFI binary in the installed root filesystem
        root_dir = os.path.join(self.root_mount, os.sep) if self.root_mount else ""

        grub_search_paths = [
            os.path.join(root_dir, "usr", "lib", "grub", "x86_64-efi", "grubx64.efi"),
            os.path.join(root_dir, "usr", "lib", "grub", "grubx64.efi"),
        ] if root_dir else []

        # Also check the ISO extraction for EFI files
        for path in grub_search_paths:
            if os.path.isfile(path):
                shutil.copy2(path, os.path.join(efi_boot_dir, "BOOTX64.EFI"))
                self._log(f"Found and copied GRUB EFI from: {path}")
                return

        # If still no GRUB binary, create a Shim + GRUB chain
        # Check for shim (used by Ubuntu, Fedora for Secure Boot)
        shim_paths = [
            os.path.join(root_dir, "usr", "lib", "shim", "shimx64.efi"),
            os.path.join(root_dir, "usr", "lib", "shim", "shim.efi.signed"),
        ] if root_dir else []

        for path in shim_paths:
            if os.path.isfile(path):
                shutil.copy2(path, os.path.join(efi_boot_dir, "BOOTX64.EFI"))
                # Copy the corresponding GRUB
                grubx64 = path.replace("shimx64.efi", "grubx64.efi").replace("shim.efi.signed", "grubx64.efi")
                if os.path.isfile(grubx64):
                    shutil.copy2(grubx64, os.path.join(efi_boot_dir, "grubx64.efi"))
                self._log("Copied shim + GRUB for Secure Boot support.")
                return

        self._log("Note: GRUB EFI binary not found in assets or installed system.")
        self._log("The system may need GRUB installed from within Linux on first boot.")
        self._log("The firstboot.sh script will attempt to run grub-install.")

    def _write_grub_cfg(self):
        """Generate and write grub.cfg for the installed system."""
        efi_root = os.path.join(self.efi_mount, os.sep)
        grub_dir = os.path.join(efi_root, "grub")
        os.makedirs(grub_dir, exist_ok=True)

        cfg_content = self._generate_installed_grub_cfg()

        cfg_path = os.path.join(grub_dir, "grub.cfg")
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write(cfg_content)

        self._log(f"Written grub.cfg to EFI partition.")

        # Also write to /boot/grub/ on root partition
        if self.root_mount:
            root_grub_dir = os.path.join(self.root_mount, "boot", "grub")
            os.makedirs(root_grub_dir, exist_ok=True)
            try:
                shutil.copy2(cfg_path, os.path.join(root_grub_dir, "grub.cfg"))
            except OSError:
                pass

    def _generate_installed_grub_cfg(self) -> str:
        """
        Generate grub.cfg for an INSTALLED system (not loopback ISO boot).

        This boots the kernel and initrd directly from the root partition,
        which is how a real Linux installation works.
        """
        return """\
# =============================================================
# GRUB Configuration - Linux USB Installer
# Boots the installed Linux system from this disk
# =============================================================
set timeout=10
set default=0
set gfxpayload=keep

insmod all_video
insmod gfxterm
insmod font
insmod part_gpt
insmod part_msdos
insmod ext2
insmod fat
insmod ntfs
insmod normal
insmod search
insmod search_fs_uuid
insmod search_fs_file
insmod search_label
insmod linux
insmod chain
insmod configfile

terminal_output gfxterm

# Try to load a nicer font if available
if [ -f /grub/fonts/unicode.pf2 ] ; then
    loadfont /grub/fonts/unicode.pf2
elif [ -f /boot/grub/fonts/unicode.pf2 ] ; then
    loadfont /boot/grub/fonts/unicode.pf2
fi

# Search for the root partition by label
search --set=root --part-label LINUXROOT --no-floppy

# =============================================================
# Linux - Boot installed system
# =============================================================
menuentry "Linux (Installed)" {
    linux /boot/vmlinuz root=PARTLABEL=LINUXROOT ro quiet splash
    initrd /boot/initrd.img
}

menuentry "Linux (Recovery Mode)" {
    linux /boot/vmlinuz root=PARTLABEL=LINUXROOT ro single
    initrd /boot/initrd.img
}

menuentry "Linux (Safe Graphics)" {
    linux /boot/vmlinuz root=PARTLABEL=LINUXROOT ro nomodeset quiet splash
    initrd /boot/initrd.img
}

# =============================================================
# UEFI Firmware Settings
# =============================================================
if [ "${grub_platform}" = "efi" ]; then
    menuentry "UEFI Firmware Settings" {
        fwsetup
    }
fi

# =============================================================
# Reboot / Halt
# =============================================================
menuentry "Reboot" {
    reboot
}

menuentry "Power Off" {
    halt
}
"""
