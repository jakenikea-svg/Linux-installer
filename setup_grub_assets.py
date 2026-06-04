#!/usr/bin/env python3
"""
GRUB Asset Setup - Prepares GRUB bootloader binaries

Run this on a Linux machine with GRUB installed to create the
assets/grub/ directory needed for building the .exe.

Usage:
    python setup_grub_assets.py
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Optional

PROJECT = Path(__file__).parent
GRUB_DIR = PROJECT / "assets" / "grub"


def find_exe(names):
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


def setup():
    print("Setting up GRUB assets...\n")
    GRUB_DIR.mkdir(parents=True, exist_ok=True)

    grub_mkimage = find_exe(["grub-mkimage", "grub2-mkimage"])
    if not grub_mkimage:
        print("grub-mkimage not found. Install GRUB: sudo apt install grub2")
        create_placeholder()
        return False

    # Find module dirs
    efi_mods = None
    bios_mods = None
    for d in ["/usr/lib/grub/x86_64-efi", "/usr/lib/grub2/x86_64-efi",
              "/usr/share/grub/x86_64-efi"]:
        if os.path.isdir(d):
            efi_mods = d
            break
    for d in ["/usr/lib/grub/i386-pc", "/usr/lib/grub2/i386-pc"]:
        if os.path.isdir(d):
            bios_mods = d
            break

    # Build standalone grubx64.efi
    if efi_mods:
        print(f"Found EFI modules: {efi_mods}")
        output = GRUB_DIR / "grubx64.efi"
        modules = [
            "all_video", "boot", "btrfs", "cat", "chain", "configfile",
            "echo", "efi_gop", "efi_uga", "ext2", "fat", "font",
            "gfxmenu", "gfxterm", "gzio", "halt", "help", "iso9660",
            "jpeg", "keystatus", "linux", "loadenv", "loopback", "ls",
            "normal", "ntfs", "ntfscomp", "part_gpt", "part_msdos",
            "png", "probe", "read", "reboot", "regexp", "search",
            "search_fs_file", "search_fs_uuid", "search_label", "sleep",
            "squash4", "terminal", "terminfo", "test", "true", "video",
            "xfs",
        ]

        embedded_cfg = 'search --set=root --file /grub/grub.cfg --no-floppy\nset prefix=($root)/grub\n'

        result = subprocess.run(
            [grub_mkimage, "-O", "x86_64-efi", "-o", str(output),
             "-p", "/grub", "-c", "-"] + modules,
            input=embedded_cfg.encode(), capture_output=True, timeout=60,
        )

        if result.returncode == 0 and output.exists():
            print(f"  Created: {output} ({output.stat().st_size / 1024:.0f} KB)")
        else:
            print(f"  grub-mkimage failed: {result.stderr.decode()[:200]}")

        # Copy modules
        mod_dst = GRUB_DIR / "x86_64-efi"
        if mod_dst.exists():
            shutil.rmtree(mod_dst)
        shutil.copytree(efi_mods, mod_dst)
        print(f"  Copied EFI modules to {mod_dst}")

    # Copy BIOS modules
    if bios_mods:
        mod_dst = GRUB_DIR / "i386-pc"
        if mod_dst.exists():
            shutil.rmtree(mod_dst)
        shutil.copytree(bios_mods, mod_dst)
        print(f"  Copied BIOS modules to {mod_dst}")

    # Copy unicode font
    for font_path in ["/usr/share/grub/unicode.pf2", "/usr/lib/grub/unicode.pf2"]:
        if os.path.isfile(font_path):
            fonts_dir = GRUB_DIR
            shutil.copy2(font_path, fonts_dir / "unicode.pf2")
            print(f"  Copied font: {font_path}")
            break

    print("\nGRUB assets ready!")
    return True


def create_placeholder():
    for d in [GRUB_DIR / "x86_64-efi", GRUB_DIR / "i386-pc"]:
        d.mkdir(parents=True, exist_ok=True)

    readme = GRUB_DIR / "README.txt"
    with open(readme, "w") as f:
        f.write("GRUB Assets\n===========\n\n"
                "Required files:\n"
                "  grubx64.efi    - UEFI boot loader\n"
                "  x86_64-efi/    - UEFI modules\n"
                "  i386-pc/       - BIOS modules\n"
                "  unicode.pf2    - Font\n\n"
                "Run: python setup_grub_assets.py (on Linux with GRUB installed)\n"
                "Or extract from Ventoy ISO\n")
    print(f"Created placeholder at {GRUB_DIR}")


if __name__ == "__main__":
    setup()
