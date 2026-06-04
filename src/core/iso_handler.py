"""
ISO Handler - Validation, Analysis, and Extraction

Handles ISO file validation, distro detection, and coordinates
with the filesystem module for extraction.
"""

import os
import re
import hashlib
import subprocess
import sys
from typing import Optional, Callable, Tuple, List
from dataclasses import dataclass


@dataclass
class ISOInfo:
    """Information about a Linux ISO file."""
    filepath: str
    filename: str
    size_bytes: int
    distro_name: str
    distro_version: str
    arch: str
    has_efi: bool
    has_bios: bool
    distro_type: str     # "casper", "live", "anaconda", "archiso", "suse", "generic"
    label: str

    @property
    def size_gb(self) -> float:
        return self.size_bytes / (1024 ** 3)

    @property
    def display_name(self) -> str:
        parts = [p for p in [self.distro_name, self.distro_version, self.arch] if p]
        return " ".join(parts) if parts else self.filename


class ISOHandler:
    """Handles ISO validation and analysis."""

    def __init__(self, callback: Optional[Callable] = None):
        self.callback = callback or (lambda x: None)

    def _log(self, msg: str):
        self.callback(msg)

    def validate_iso(self, filepath: str) -> Tuple[bool, str]:
        """Validate an ISO file."""
        if not os.path.isfile(filepath):
            return False, "File does not exist."
        if not filepath.lower().endswith('.iso'):
            return False, "Must be a .iso file."
        size = os.path.getsize(filepath)
        if size < 100 * 1024 * 1024:
            return False, f"File too small ({size / (1024*1024):.0f} MB). Expected a Linux ISO."

        # Check ISO 9660 signature
        try:
            with open(filepath, 'rb') as f:
                f.seek(32768)
                if f.read(5) != b'CD001':
                    self._log("Warning: May not be standard ISO 9660.")
        except Exception as e:
            return False, f"Cannot read file: {e}"

        return True, "Valid ISO."

    def analyze_iso(self, filepath: str) -> ISOInfo:
        """Analyze ISO and return detailed info."""
        filename = os.path.basename(filepath)
        size = os.path.getsize(filepath)

        info = ISOInfo(
            filepath=filepath, filename=filename, size_bytes=size,
            distro_name="", distro_version="", arch="",
            has_efi=False, has_bios=False, distro_type="generic",
            label="",
        )

        self._parse_filename(filename, info)
        self._inspect_contents(filepath, info)
        info.label = self._read_label(filepath)

        return info

    def _parse_filename(self, filename: str, info: ISOInfo):
        """Detect distro from filename."""
        name = filename.lower()

        distros = {
            "Ubuntu": ["ubuntu"], "Debian": ["debian"],
            "Linux Mint": ["linuxmint", "linux-mint"],
            "Fedora": ["fedora"], "CentOS": ["centos"],
            "Rocky Linux": ["rocky"], "AlmaLinux": ["almalinux"],
            "Arch Linux": ["archlinux", "arch"],
            "Manjaro": ["manjaro"], "openSUSE": ["opensuse", "tumbleweed", "leap"],
            "Kali Linux": ["kali"], "Pop!_OS": ["pop-os", "popos"],
            "Zorin OS": ["zorin"], "MX Linux": ["mx-linux", "mxlinux"],
            "Alpine Linux": ["alpine"], "Gentoo": ["gentoo"],
            "Void Linux": ["void"], "Slackware": ["slackware"],
            "Elementary OS": ["elementary"],
        }
        for dname, patterns in distros.items():
            if any(p in name for p in patterns):
                info.distro_name = dname
                break

        # Version
        for pat in [r'(\d{2}\.\d{2})', r'[-_](\d{2,3})[-_.]']:
            m = re.search(pat, filename)
            if m:
                info.distro_version = m.group(1)
                break

        # Arch
        for arch, keys in {"x86_64": ["amd64", "x86_64", "x64"],
                           "aarch64": ["arm64", "aarch64"],
                           "i386": ["i386", "i686"]}.items():
            if any(k in name for k in keys):
                info.arch = arch
                break
        if not info.arch:
            info.arch = "x86_64"

    def _inspect_contents(self, filepath: str, info: ISOInfo):
        """Inspect ISO contents using 7z."""
        seven_zip = self._find_7z()
        if not seven_zip:
            info.has_efi = True
            info.has_bios = True
            info.distro_type = "generic"
            return

        try:
            r = subprocess.run([seven_zip, "l", filepath], capture_output=True, text=True, timeout=30)
            listing = r.stdout.lower()

            info.has_efi = any(x in listing for x in ["efi/boot", "grubx64.efi", "bootx64.efi"])
            info.has_bios = any(x in listing for x in ["isolinux", "boot/grub"])

            if "casper" in listing:
                info.distro_type = "casper"
            elif "live/vmlinuz" in listing or "live/initrd" in listing:
                info.distro_type = "live"
            elif "isolinux" in listing and "vmlinuz" in listing:
                info.distro_type = "anaconda"
            elif "arch/boot" in listing:
                info.distro_type = "archiso"
            elif "boot/x86_64/loader" in listing:
                info.distro_type = "suse"
            else:
                info.distro_type = "generic"

        except Exception:
            pass

    def _read_label(self, filepath: str) -> str:
        """Read ISO volume label."""
        try:
            with open(filepath, 'rb') as f:
                f.seek(32808)
                return f.read(32).decode('ascii', errors='ignore').strip()
        except Exception:
            return ""

    def _find_7z(self) -> Optional[str]:
        """Find 7z."""
        for c in (["7z", "7z.exe", r"C:\Program Files\7-Zip\7z.exe",
                    r"C:\Program Files (x86)\7-Zip\7z.exe"] if sys.platform == "win32"
                  else ["7z", "7za"]):
            try:
                subprocess.run([c, "--help"], capture_output=True, timeout=5)
                return c
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        return None
