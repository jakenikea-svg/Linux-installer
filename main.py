#!/usr/bin/env python3
"""
Linux OS Installer - Main Entry Point

Installs Linux from an ISO directly onto USB, HDD, or SD card.
Handles partitioning, GRUB, OS extraction, and system configuration.

Usage:
    python main.py              # GUI wizard
    python main.py --cli        # Command line mode
    python main.py --check      # Check dependencies
"""

import os
import sys
import argparse


def check_deps():
    missing = []
    for mod in ["ttkbootstrap", "psutil", "requests", "PIL"]:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        print(f"Missing: {', '.join(missing)}")
        print(f"Install: pip install {' '.join(missing)}")
        return False
    print("All dependencies OK.")
    return True


def run_gui():
    if not check_deps():
        sys.exit(1)
    from src.gui.wizard import main
    main()


def run_cli():
    from src.core.disk_manager import DiskDetector, DiskFormatter
    from src.core.iso_handler import ISOHandler
    from src.core.install_engine import InstallEngine, InstallPhase
    from src.core.filesystem import InstallConfig

    print("=" * 55)
    print("  Linux OS Installer - CLI Mode")
    print("=" * 55)

    if not DiskFormatter.is_admin():
        print("\nERROR: Run as administrator/root.")
        sys.exit(1)

    # ISO
    print("\nStep 1: Select ISO")
    iso_path = input("  ISO path: ").strip().strip('"')
    if not os.path.isfile(iso_path):
        print("  File not found.")
        sys.exit(1)

    handler = ISOHandler()
    ok, msg = handler.validate_iso(iso_path)
    if not ok:
        print(f"  Invalid: {msg}")
        sys.exit(1)
    info = handler.analyze_iso(iso_path)
    print(f"  Detected: {info.display_name} ({info.size_gb:.1f} GB)")

    # Disk
    print("\nStep 2: Select Target Drive")
    detector = DiskDetector()
    disks = detector.detect_all()
    for i, d in enumerate(disks):
        print(f"  [{i}] {d.display_name}")
    if not disks:
        print("  No drives found.")
        sys.exit(1)
    idx = int(input("\n  Drive number: ").strip())
    if idx < 0 or idx >= len(disks):
        print("  Invalid.")
        sys.exit(1)
    disk = disks[idx]

    # Boot mode
    print("\nStep 3: Boot Mode")
    print("  [1] Hybrid (Recommended)  [2] UEFI Only  [3] BIOS Only")
    mode_map = {"1": "hybrid", "2": "uefi", "3": "bios"}
    boot_mode = mode_map.get(input("  Choice: ").strip(), "hybrid")

    # Settings
    hostname = input("\n  Hostname [linux]: ").strip() or "linux"
    username = input("  Username [user]: ").strip() or "user"

    # Confirm
    print(f"\n  ISO: {os.path.basename(iso_path)}")
    print(f"  Target: {disk.display_name}")
    print(f"  Boot: {boot_mode}")
    print(f"  WARNING: All data on target will be erased!")
    if input("\n  Proceed? (yes/no): ").strip().lower() != "yes":
        print("  Cancelled.")
        sys.exit(0)

    # Install
    config = InstallConfig(hostname=hostname, username=username)
    engine = InstallEngine(
        iso_path=iso_path, target_disk=disk,
        boot_mode=boot_mode, install_config=config,
        callback=lambda p, pr, m: print(f"  [{p.value}] ({pr*100:.0f}%) {m}"),
    )
    ok, msg = engine.run()
    print(f"\n  {'SUCCESS' if ok else 'FAILED'}: {msg}")


def main():
    parser = argparse.ArgumentParser(description="Linux OS Installer")
    parser.add_argument("--cli", action="store_true", help="CLI mode")
    parser.add_argument("--check", action="store_true", help="Check deps")
    args = parser.parse_args()

    if args.check:
        check_deps()
    elif args.cli:
        run_cli()
    else:
        run_gui()


if __name__ == "__main__":
    main()
