# Linux OS Installer

**Installs Linux from an ISO directly onto a drive** — USB, HDD, SD card. Not a bootable USB maker — this actually INSTALLS the OS and sets up GRUB, like the Windows installer does.

---

## How to Get the .exe (3 Ways)

### Way 1: GitHub Actions (Easiest — Compiles Online for Free)

This is how you compile it online. You don't need Windows or Python installed.

**Step by step:**

1. **Create a GitHub account** (free) at https://github.com/signup
2. **Create a new repository**:
   - Click the **+** icon → **New repository**
   - Name it `linux-installer`
   - Make it Private or Public
   - Click **Create repository**
3. **Upload the code**:
   - Click **uploading an existing file**
   - Drag the entire `linux-usb-installer` folder contents into the browser
   - Or use git: `git push origin main`
4. **Wait for the build** (starts automatically):
   - Go to the **Actions** tab in your repo
   - You'll see "Build Windows .exe" running
   - Wait ~3 minutes until it shows a green checkmark ✓
5. **Download the .exe**:
   - Click the completed workflow run
   - Scroll down to **Artifacts**
   - Click **LinuxOSInstaller-exe** to download the .exe

That's it. You now have `LinuxOSInstaller.exe`.

### Way 2: Build on Your Own Windows PC

If you have a Windows computer:

```cmd
:: 1. Install Python from python.org
:: 2. Install 7-Zip from 7-zip.org
:: 3. Open Command Prompt and run:

pip install pyinstaller ttkbootstrap psutil requests Pillow
cd linux-usb-installer
pyinstaller --onefile --name LinuxOSInstaller --noconfirm --collect-all ttkbootstrap main.py

:: The .exe will be in dist\LinuxOSInstaller.exe
```

### Way 3: Use Google Colab (Free)

Open https://colab.research.google.com and paste this in a cell:

```python
!apt-get update && apt-get install -y python3-pip
!pip install pyinstaller ttkbootstrap psutil requests Pillow
# Upload your code files, then:
!pyinstaller --onefile --name LinuxOSInstaller main.py
# Download the .exe from the files panel
```

> **Note**: Google Colab runs Linux, so it produces a Linux binary, not a Windows .exe. For a Windows .exe, use GitHub Actions (Way 1).

---

## How to Use the .exe

1. Make sure **7-Zip** is installed (https://7-zip.org)
2. **Right-click** `LinuxOSInstaller.exe` → **Run as administrator**
3. Follow the wizard:
   - Select your downloaded Linux ISO
   - Choose your target drive (USB, HDD, SD card)
   - Pick boot mode (Hybrid recommended)
   - Click **Install**
4. When done, boot from the drive — Linux is installed and ready!

---

## What It Does

| Step | What Happens |
|------|-------------|
| 1 | Partitions the target drive (EFI + Swap + Root) |
| 2 | Extracts the full OS from the ISO's squashfs |
| 3 | Installs GRUB bootloader for UEFI/BIOS boot |
| 4 | Copies kernel (vmlinuz) and initrd to /boot/ |
| 5 | Configures fstab, hostname, networking |
| 6 | Sets up first-boot script to create your user |
| 7 | Boots into installed Linux directly |

---

## Supported Media & Distros

**Media**: USB flash drive, external HDD/SSD, SD card, memory stick, internal drive

**Distros**: Ubuntu, Debian, Linux Mint, Fedora, CentOS, Rocky, Alma, Arch, Manjaro, openSUSE, Kali, Pop!_OS, Zorin, MX Linux, Alpine, Gentoo, Void, and more. Unknown distros get generic boot entries.

---

## Project Structure

```
linux-usb-installer/
├── main.py                      # Entry point
├── build.py                     # Build script
├── setup_grub_assets.py         # GRUB binary setup (run on Linux)
├── requirements.txt
├── .github/workflows/build.yml  # ← Online build (GitHub Actions)
└── src/
    ├── core/
    │   ├── disk_manager.py      # Detect all disk types
    │   ├── filesystem.py        # Extract OS, install to disk
    │   ├── grub_installer.py    # Install GRUB bootloader
    │   ├── iso_handler.py       # ISO validation & analysis
    │   └── install_engine.py    # Full install pipeline
    └── gui/
        └── wizard.py            # 7-step wizard GUI
```
