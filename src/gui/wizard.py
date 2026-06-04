"""
Linux USB Installer - Wizard GUI

A professional installer wizard that installs Linux from an ISO
directly onto a target disk (USB, HDD, SD card).

Steps:
  1. Welcome
  2. Select ISO
  3. Select Target Disk
  4. Boot Mode & Settings
  5. Confirm
  6. Installing
  7. Complete
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Optional

try:
    import ttkbootstrap as ttk
except ImportError:
    import tkinter.ttk as ttk

from src.core.disk_manager import DiskDevice, DiskDetector, DiskFormatter
from src.core.iso_handler import ISOHandler, ISOInfo
from src.core.install_engine import InstallEngine, InstallPhase
from src.core.filesystem import InstallConfig


WINDOW_W = 740
WINDOW_H = 560
TITLE = "Linux OS Installer"
SUBTITLE = "Install Linux directly onto USB, HDD, or SD Card"


class WizardApp(ttk.Window if hasattr(ttk, 'Window') else tk.Tk):
    def __init__(self):
        if hasattr(ttk, 'Window'):
            super().__init__(themename="darkly")
        else:
            super().__init__()
            self.configure(bg="#1a1a2e")

        self.title(TITLE)
        self.geometry(f"{WINDOW_W}x{WINDOW_H}")
        self.resizable(False, False)

        # Center
        self.update_idletasks()
        x = (self.winfo_screenwidth() - WINDOW_W) // 2
        y = (self.winfo_screenheight() - WINDOW_H) // 2
        self.geometry(f"{WINDOW_W}x{WINDOW_H}+{x}+{y}")

        # State
        self.step = 0
        self.total_steps = 7
        self.iso_path = ""
        self.iso_info: Optional[ISOInfo] = None
        self.selected_disk: Optional[DiskDevice] = None
        self.boot_mode = "hybrid"
        self.install_config = InstallConfig()
        self.disks = []
        self.install_success = False
        self.install_message = ""

        self.step_names = ["Welcome", "Select ISO", "Select Disk", "Settings", "Confirm", "Installing", "Done"]
        self.frames = {}

        self._build_ui()
        self._show_step(0)

    def _build_ui(self):
        # Header
        hdr = ttk.Frame(self)
        hdr.pack(fill="x", padx=0, pady=0)
        ttk.Label(hdr, text=TITLE, font=("Segoe UI", 18, "bold")).pack(pady=(12, 0))
        ttk.Label(hdr, text=SUBTITLE, font=("Segoe UI", 9)).pack(pady=(0, 5))

        # Step indicators
        self.indicators = []
        ind_frame = ttk.Frame(self)
        ind_frame.pack(fill="x", padx=15, pady=(2, 0))
        for i, name in enumerate(self.step_names):
            f = ttk.Frame(ind_frame)
            f.pack(side="left", expand=True)
            c = ttk.Label(f, text=str(i+1), font=("Segoe UI", 9, "bold"), anchor="center", width=3)
            c.pack()
            l = ttk.Label(f, text=name, font=("Segoe UI", 7), anchor="center")
            l.pack()
            self.indicators.append((c, l))

        # Content
        self.content = ttk.Frame(self)
        self.content.pack(fill="both", expand=True, padx=20, pady=8)

        self._build_welcome()
        self._build_iso()
        self._build_disk()
        self._build_settings()
        self._build_confirm()
        self._build_installing()
        self._build_complete()

        # Navigation
        nav = ttk.Frame(self)
        nav.pack(fill="x", padx=20, pady=(0, 12))
        self.btn_back = ttk.Button(nav, text="< Back", command=self._back, width=12)
        self.btn_back.pack(side="left")
        self.btn_cancel = ttk.Button(nav, text="Cancel", command=self._cancel, width=12)
        self.btn_cancel.pack(side="right", padx=5)
        self.btn_next = ttk.Button(nav, text="Next >", command=self._next, width=12)
        self.btn_next.pack(side="right")

    # --- Step 1: Welcome ---
    def _build_welcome(self):
        f = ttk.Frame(self.content)
        self.frames[0] = f

        ttk.Label(f, text="Install Linux on a Drive", font=("Segoe UI", 15, "bold")).pack(pady=(25, 8))
        ttk.Label(f, text="This wizard installs Linux from an ISO directly onto your\n"
                          "target drive — USB flash drive, external HDD, SD card, etc.\n\n"
                          "It handles everything automatically:",
                  font=("Segoe UI", 9), justify="center").pack(pady=(0, 12))

        features = [
            ("Partitioning", "Partitions and formats the target drive for Linux"),
            ("OS Extraction", "Extracts the full Linux OS from the ISO and installs it"),
            ("GRUB Bootloader", "Installs GRUB so the drive boots into Linux directly"),
            ("System Config", "Sets up fstab, hostname, networking, user account"),
            ("First Boot", "Creates user and finalizes setup on first boot"),
        ]
        for title, desc in features:
            row = ttk.Frame(f)
            row.pack(fill="x", padx=60, pady=2)
            ttk.Label(row, text=f"  {title}:", font=("Segoe UI", 9, "bold"), width=16, anchor="w").pack(side="left")
            ttk.Label(row, text=desc, font=("Segoe UI", 9), anchor="w").pack(side="left", fill="x", expand=True)

        ttk.Label(f, text="\nYou need:\n  - A Linux ISO file (already downloaded)\n"
                          "  - A target drive (USB, HDD, SD card — min 4 GB)\n"
                          "  - 7-Zip installed (https://7-zip.org)\n"
                          "  - Administrator privileges",
                  font=("Segoe UI", 9), justify="left").pack(pady=(12, 0), padx=60, anchor="w")

    # --- Step 2: ISO ---
    def _build_iso(self):
        f = ttk.Frame(self.content)
        self.frames[1] = f

        ttk.Label(f, text="Select Linux ISO", font=("Segoe UI", 13, "bold")).pack(pady=(15, 5))
        ttk.Label(f, text="Choose the Linux distribution ISO you downloaded.", font=("Segoe UI", 9)).pack(pady=(0, 10))

        pf = ttk.Frame(f)
        pf.pack(fill="x", padx=40)
        self.iso_path_var = tk.StringVar()
        ttk.Entry(pf, textvariable=self.iso_path_var, font=("Segoe UI", 9)).pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Button(pf, text="Browse...", command=self._browse_iso, width=10).pack(side="right")

        self.iso_info_frame = ttk.LabelFrame(f, text="ISO Information", padding=8)
        self.iso_info_frame.pack(fill="x", padx=40, pady=12)

        self.iso_labels = {}
        for label, key in [("Distribution", "distro"), ("Version", "ver"), ("Architecture", "arch"),
                           ("Size", "size"), ("Boot Type", "type"), ("UEFI", "efi"), ("BIOS", "bios")]:
            row = ttk.Frame(self.iso_info_frame)
            row.pack(fill="x", pady=1)
            ttk.Label(row, text=f"{label}:", font=("Segoe UI", 9, "bold"), width=14, anchor="w").pack(side="left")
            lbl = ttk.Label(row, text="-", font=("Segoe UI", 9), anchor="w")
            lbl.pack(side="left", fill="x", expand=True)
            self.iso_labels[key] = lbl

        self.iso_status = ttk.Label(f, text="", font=("Segoe UI", 9))
        self.iso_status.pack(pady=3)

    def _browse_iso(self):
        path = filedialog.askopenfilename(title="Select Linux ISO", filetypes=[("ISO", "*.iso"), ("All", "*.*")])
        if path:
            self.iso_path_var.set(path)
            self._validate_iso()

    def _validate_iso(self):
        path = self.iso_path_var.get()
        if not path or not os.path.isfile(path):
            self.iso_status.configure(text="Select a valid ISO file.", foreground="orange")
            self.iso_info = None
            return

        handler = ISOHandler()
        ok, msg = handler.validate_iso(path)
        if ok:
            self.iso_info = handler.analyze_iso(path)
            self.iso_path = path
            self.iso_labels["distro"].configure(text=self.iso_info.distro_name or "Unknown")
            self.iso_labels["ver"].configure(text=self.iso_info.distro_version or "-")
            self.iso_labels["arch"].configure(text=self.iso_info.arch or "-")
            self.iso_labels["size"].configure(text=f"{self.iso_info.size_gb:.2f} GB")
            self.iso_labels["type"].configure(text=self.iso_info.distro_type)
            self.iso_labels["efi"].configure(text="Yes" if self.iso_info.has_efi else "No")
            self.iso_labels["bios"].configure(text="Yes" if self.iso_info.has_bios else "No")
            self.iso_status.configure(text="Valid ISO selected.", foreground="green")
        else:
            self.iso_status.configure(text=f"Invalid: {msg}", foreground="red")
            self.iso_info = None

    # --- Step 3: Disk ---
    def _build_disk(self):
        f = ttk.Frame(self.content)
        self.frames[2] = f

        ttk.Label(f, text="Select Target Drive", font=("Segoe UI", 13, "bold")).pack(pady=(15, 5))
        ttk.Label(f, text="Choose the drive to install Linux on.\n"
                          "ALL DATA on the selected drive will be permanently erased!",
                  font=("Segoe UI", 9), justify="center").pack(pady=(0, 10))

        lf = ttk.Frame(f)
        lf.pack(fill="both", expand=True, padx=40)

        cols = ("type", "drive", "label", "size", "model", "fs")
        self.disk_tree = ttk.Treeview(lf, columns=cols, show="headings", height=6, selectmode="browse")
        for col, heading, width in [("type", "Type", 70), ("drive", "Drive", 55),
                                     ("label", "Label", 80), ("size", "Size", 75),
                                     ("model", "Model", 160), ("fs", "FS", 60)]:
            self.disk_tree.heading(col, text=heading)
            self.disk_tree.column(col, width=width, anchor="center" if col in ("type","drive","size","fs") else "w")
        self.disk_tree.pack(fill="both", expand=True)

        bf = ttk.Frame(f)
        bf.pack(fill="x", padx=40, pady=8)
        ttk.Button(bf, text="Refresh", command=self._refresh_disks, width=12).pack(side="left")
        self.disk_label = ttk.Label(bf, text="", font=("Segoe UI", 9))
        self.disk_label.pack(side="right")

        self.disk_tree.bind("<<TreeviewSelect>>", self._on_disk_select)

    def _refresh_disks(self):
        for item in self.disk_tree.get_children():
            self.disk_tree.delete(item)

        detector = DiskDetector()
        self.disks = detector.detect_all()

        for d in self.disks:
            self.disk_tree.insert("", "end", values=(
                d.media_type, d.drive_letter, d.label or "-",
                f"{d.size_gb:.1f} GB", d.model or "-", d.filesystem or "-"
            ))

        if not self.disks:
            self.disk_label.configure(text="No drives detected. Connect a drive and click Refresh.", foreground="orange")
        else:
            self.disk_label.configure(text=f"Found {len(self.disks)} drive(s)", foreground="green")

    def _on_disk_select(self, event):
        sel = self.disk_tree.selection()
        if sel:
            idx = self.disk_tree.index(sel[0])
            if idx < len(self.disks):
                self.selected_disk = self.disks[idx]
                self.disk_label.configure(text=f"Selected: {self.selected_disk.display_name}", foreground="green")

    # --- Step 4: Settings ---
    def _build_settings(self):
        f = ttk.Frame(self.content)
        self.frames[3] = f

        ttk.Label(f, text="Installation Settings", font=("Segoe UI", 13, "bold")).pack(pady=(15, 5))

        # Boot mode
        ttk.Label(f, text="Boot Mode:", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=40, pady=(10, 3))
        self.boot_mode_var = tk.StringVar(value="hybrid")
        for val, text, desc in [
            ("hybrid", "Hybrid (BIOS + UEFI)", "Works on any computer. Recommended."),
            ("uefi", "UEFI Only", "Modern computers (2012+). May need Secure Boot disabled."),
            ("bios", "BIOS Only", "Older computers with legacy BIOS."),
        ]:
            row = ttk.Frame(f)
            row.pack(fill="x", padx=55, pady=1)
            ttk.Radiobutton(row, text=text, variable=self.boot_mode_var, value=val).pack(anchor="w")
            ttk.Label(row, text=desc, font=("Segoe UI", 8)).pack(anchor="w", padx=22)

        # System settings
        settings_frame = ttk.LabelFrame(f, text="System Settings", padding=8)
        settings_frame.pack(fill="x", padx=40, pady=(15, 5))

        self.hostname_var = tk.StringVar(value="linux")
        self.username_var = tk.StringVar(value="user")
        self.tz_var = tk.StringVar(value="UTC")

        for label, var, row_idx in [("Hostname:", self.hostname_var, 0),
                                     ("Username:", self.username_var, 1),
                                     ("Timezone:", self.tz_var, 2)]:
            row = ttk.Frame(settings_frame)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=label, font=("Segoe UI", 9, "bold"), width=12, anchor="w").pack(side="left")
            ttk.Entry(row, textvariable=var, font=("Segoe UI", 9), width=25).pack(side="left", padx=5)

    # --- Step 5: Confirm ---
    def _build_confirm(self):
        f = ttk.Frame(self.content)
        self.frames[4] = f

        ttk.Label(f, text="Review & Confirm", font=("Segoe UI", 13, "bold")).pack(pady=(15, 5))
        ttk.Label(f, text="Review your settings. Click Install to begin.",
                  font=("Segoe UI", 9)).pack(pady=(0, 10))

        self.confirm_frame = ttk.LabelFrame(f, text="Installation Summary", padding=12)
        self.confirm_frame.pack(fill="x", padx=40, pady=5)

        self.confirm_labels = {}
        for label, key in [("ISO File", "iso"), ("Distribution", "distro"), ("ISO Size", "iso_size"),
                           ("Target Drive", "disk"), ("Drive Size", "disk_size"), ("Drive Type", "disk_type"),
                           ("Boot Mode", "bootmode"), ("Hostname", "hostname"), ("Username", "username")]:
            row = ttk.Frame(self.confirm_frame)
            row.pack(fill="x", pady=1)
            ttk.Label(row, text=f"{label}:", font=("Segoe UI", 9, "bold"), width=14, anchor="w").pack(side="left")
            lbl = ttk.Label(row, text="-", font=("Segoe UI", 9), anchor="w")
            lbl.pack(side="left", fill="x", expand=True)
            self.confirm_labels[key] = lbl

        ttk.Label(f, text="\nWARNING: ALL DATA on the target drive will be erased permanently!",
                  font=("Segoe UI", 10, "bold"), foreground="red", justify="center").pack(pady=(8, 0))

    def _update_confirm(self):
        if self.iso_info:
            self.confirm_labels["iso"].configure(text=os.path.basename(self.iso_path))
            self.confirm_labels["distro"].configure(text=self.iso_info.display_name)
            self.confirm_labels["iso_size"].configure(text=f"{self.iso_info.size_gb:.2f} GB")
        if self.selected_disk:
            self.confirm_labels["disk"].configure(text=self.selected_disk.display_name)
            self.confirm_labels["disk_size"].configure(text=f"{self.selected_disk.size_gb:.1f} GB")
            self.confirm_labels["disk_type"].configure(text=self.selected_disk.media_type)
        mode_names = {"hybrid": "Hybrid (BIOS+UEFI)", "uefi": "UEFI Only", "bios": "BIOS Only"}
        self.confirm_labels["bootmode"].configure(text=mode_names.get(self.boot_mode, self.boot_mode))
        self.confirm_labels["hostname"].configure(text=self.install_config.hostname)
        self.confirm_labels["username"].configure(text=self.install_config.username)

    # --- Step 6: Installing ---
    def _build_installing(self):
        f = ttk.Frame(self.content)
        self.frames[5] = f

        ttk.Label(f, text="Installing Linux...", font=("Segoe UI", 13, "bold")).pack(pady=(15, 5))

        self.phase_label = ttk.Label(f, text="Preparing...", font=("Segoe UI", 10))
        self.phase_label.pack(pady=(0, 8))

        self.progress = ttk.Progressbar(f, length=500, mode="determinate", maximum=100)
        self.progress.pack(pady=(0, 3))

        self.pct_label = ttk.Label(f, text="0%", font=("Segoe UI", 9))
        self.pct_label.pack()

        log_frame = ttk.LabelFrame(f, text="Installation Log", padding=5)
        log_frame.pack(fill="both", expand=True, padx=35, pady=(8, 0))

        self.log_text = tk.Text(log_frame, height=8, font=("Consolas", 8), wrap="word",
                                state="disabled", bg="#1e1e2e", fg="#a0d0a0")
        self.log_text.pack(fill="both", expand=True)

    def _log_install(self, phase: InstallPhase, progress: float, msg: str):
        self.after(0, self._update_install_ui, phase, progress, msg)

    def _update_install_ui(self, phase: InstallPhase, progress: float, msg: str):
        self.phase_label.configure(text=phase.value)
        self.progress["value"] = progress * 100
        self.pct_label.configure(text=f"{progress*100:.0f}%")

        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{phase.value}] {msg}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

        if phase == InstallPhase.COMPLETE:
            self.install_success = True
            self.install_message = msg
            self._advance_after_install()
        elif phase == InstallPhase.FAILED:
            self.install_success = False
            self.install_message = msg
            self._advance_after_install()

    def _advance_after_install(self):
        self.btn_next.configure(state="normal")
        self.btn_cancel.configure(state="disabled")
        self.btn_next.configure(text="Finish" if self.install_success else "Close")
        self.step = 6
        self._show_step(6)

    def _start_install(self):
        self.install_config.hostname = self.hostname_var.get() or "linux"
        self.install_config.username = self.username_var.get() or "user"
        self.install_config.timezone = self.tz_var.get() or "UTC"

        engine = InstallEngine(
            iso_path=self.iso_path,
            target_disk=self.selected_disk,
            boot_mode=self.boot_mode,
            install_config=self.install_config,
            callback=self._log_install,
        )
        t = threading.Thread(target=engine.run, daemon=True)
        t.start()

    # --- Step 7: Complete ---
    def _build_complete(self):
        f = ttk.Frame(self.content)
        self.frames[6] = f

        self.done_title = ttk.Label(f, text="", font=("Segoe UI", 16, "bold"))
        self.done_title.pack(pady=(30, 8))

        self.done_msg = ttk.Label(f, text="", font=("Segoe UI", 10), justify="center", wraplength=500)
        self.done_msg.pack(pady=(0, 12))

        instr = ttk.LabelFrame(f, text="How to Boot Your Installed Linux", padding=12)
        instr.pack(fill="x", padx=50, pady=5)

        for txt in [
            "1. Keep the drive connected and restart your computer.",
            "2. Press the boot menu key during startup (F12, F8, or Esc).",
            "3. Select your drive from the boot menu.",
            "4. GRUB will appear — choose 'Linux (Installed)'.",
            "5. On first boot, your user account will be created automatically.",
            "6. Default password is: linux (change it after first login!)",
        ]:
            ttk.Label(instr, text=txt, font=("Segoe UI", 9), anchor="w").pack(fill="x", pady=1)

        keys = ttk.LabelFrame(f, text="Common Boot Menu Keys", padding=8)
        keys.pack(fill="x", padx=50, pady=5)
        ttk.Label(keys, text="Dell: F12 | HP: F9 | Lenovo: F12 | ASUS: F8/Esc | Acer: F12",
                  font=("Segoe UI", 8), anchor="center").pack()

    # --- Navigation ---
    def _show_step(self, step):
        for frame in self.frames.values():
            frame.pack_forget()
        if step in self.frames:
            self.frames[step].pack(fill="both", expand=True)

        self.btn_back.configure(state="disabled" if step in (0, 5) else "normal")
        self.btn_cancel.configure(state="disabled" if step in (5, 6) else "normal")

        if step == 6:
            self.btn_next.configure(text="Finish")
            self.btn_next.configure(state="normal")
            self._update_complete()
        elif step == 4:
            self.btn_next.configure(text="Install")
            self._update_confirm()
        elif step == 5:
            self.btn_next.configure(state="disabled")
            self.btn_next.configure(text="Installing...")
        else:
            self.btn_next.configure(text="Next >")
            self.btn_next.configure(state="normal")

    def _update_complete(self):
        if self.install_success:
            self.done_title.configure(text="Installation Complete!")
            self.done_msg.configure(text="Linux has been installed on your drive.\n"
                                         "You can now boot from it and use your installed Linux system.")
        else:
            self.done_title.configure(text="Installation Failed")
            self.done_msg.configure(text=f"The installation did not complete.\n\n"
                                         f"Error: {self.install_message}\n\n"
                                         f"Check the log above for details.")

    def _next(self):
        if self.step == 1:
            self.iso_path = self.iso_path_var.get()
            self._validate_iso()
            if not self.iso_info:
                messagebox.showwarning("No ISO", "Select a valid Linux ISO file.")
                return
        elif self.step == 2:
            if not self.selected_disk:
                messagebox.showwarning("No Drive", "Select a target drive.")
                return
        elif self.step == 3:
            self.boot_mode = self.boot_mode_var.get()
            self.install_config.hostname = self.hostname_var.get() or "linux"
            self.install_config.username = self.username_var.get() or "user"
        elif self.step == 4:
            if not messagebox.askyesno("Confirm", f"All data on {self.selected_disk.display_name} will be erased.\n\nProceed?"):
                return
            self.step = 5
            self._show_step(5)
            self._start_install()
            return
        elif self.step == 6:
            self.destroy()
            return

        self.step += 1
        if self.step >= self.total_steps:
            self.step = self.total_steps - 1
        self._show_step(self.step)

        # Auto-refresh disk list
        if self.step == 2:
            self._refresh_disks()

    def _back(self):
        if self.step > 0 and self.step != 5:
            self.step -= 1
            self._show_step(self.step)

    def _cancel(self):
        if messagebox.askyesno("Exit", "Are you sure you want to exit?"):
            self.destroy()


def main():
    if sys.platform == "win32" and not DiskFormatter.is_admin():
        if messagebox.askyesno("Admin Required",
                               "This app needs administrator privileges.\nRestart as admin?"):
            DiskFormatter.relaunch_as_admin()
        sys.exit(1)

    app = WizardApp()
    app.mainloop()


if __name__ == "__main__":
    main()
