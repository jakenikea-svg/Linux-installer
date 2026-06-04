#!/usr/bin/env python3
"""
Build Script - Creates LinuxOSInstaller.exe via PyInstaller

Usage:
    python build.py              # Directory build (faster startup)
    python build.py --onefile    # Single .exe file
    python build.py --clean      # Remove build artifacts
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

PROJECT = Path(__file__).parent
APP_NAME = "LinuxOSInstaller"
APP_VERSION = "1.0.0"
ASSETS = PROJECT / "assets"


def clean():
    print("Cleaning...")
    for d in [PROJECT / "build", PROJECT / "dist"]:
        if d.exists():
            shutil.rmtree(d)
            print(f"  Removed {d}")
    spec = PROJECT / f"{APP_NAME}.spec"
    if spec.exists():
        spec.unlink()
    print("Done.")


def build(onefile=False):
    print(f"Building {APP_NAME} v{APP_VERSION}...")

    ASSETS.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--windowed",
        "--noconfirm",
        "--clean",
    ]

    # Add assets if they exist
    if ASSETS.exists() and any(ASSETS.iterdir()):
        cmd.extend(["--add-data", f"{ASSETS};assets"])
        print(f"  Including assets from {ASSETS}")

    # Hidden imports
    for imp in ["ttkbootstrap", "psutil", "requests", "PIL",
                "src.core.disk_manager", "src.core.grub_installer",
                "src.core.iso_handler", "src.core.install_engine",
                "src.core.filesystem", "src.gui.wizard"]:
        cmd.extend(["--hidden-import", imp])

    if onefile:
        cmd.append("--onefile")
        print("  Mode: single .exe")
    else:
        cmd.append("--onedir")
        print("  Mode: directory")

    cmd.append(str(PROJECT / "main.py"))

    print(f"\n  Running PyInstaller...\n")
    result = subprocess.run(cmd, cwd=str(PROJECT))

    if result.returncode == 0:
        out = PROJECT / "dist"
        print(f"\n{'='*55}")
        print(f"  BUILD SUCCESSFUL!")
        if onefile:
            print(f"  File: {out / APP_NAME}.exe")
        else:
            print(f"  Dir: {out / APP_NAME}/")
        print(f"  Run as Administrator on a Windows machine.")
        print(f"{'='*55}")
    else:
        print(f"\n  BUILD FAILED (exit code {result.returncode})")
        sys.exit(1)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--onefile", action="store_true")
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    if args.clean:
        clean()
    else:
        build(onefile=args.onefile)
