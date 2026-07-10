"""
Windows Tweaks GUI — kubsonxtm
Requirements: pip install customtkinter
"""

import customtkinter as ctk
import subprocess
import threading
import os
import sys
import ctypes
import tempfile
import urllib.request
import webbrowser
from pathlib import Path

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

GITHUB_RAW = "https://raw.githubusercontent.com/kubsonxtm/Windows-Tweaks/main"
TEMP_DIR = Path(tempfile.gettempdir()) / "WinTweaksGUI"
TEMP_DIR.mkdir(exist_ok=True)
PRG = "5 Programs to tweak or increase privacy"

# ── Admin ─────────────────────────────────────────────────────────────────────
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_as_admin():
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, f'"{os.path.abspath(__file__)}"', None, 1
    )
    sys.exit()

# ── Logger ────────────────────────────────────────────────────────────────────
class Logger:
    def __init__(self, textbox):
        self.tb = textbox

    def log(self, msg: str, tag: str = "info"):
        self.tb.configure(state="normal")
        self.tb.insert("end", msg + "\n")
        self.tb.see("end")
        self.tb.configure(state="disabled")

# ── GitHub download ───────────────────────────────────────────────────────────
def gh_download(logger, repo_path: str):
    url = GITHUB_RAW + "/" + urllib.request.quote(repo_path, safe="/")
    local = TEMP_DIR / Path(repo_path).name
    logger.log(f"   Downloading: {Path(repo_path).name} ...")
    try:
        urllib.request.urlretrieve(url, local)
        logger.log(f"   OK: {local.name}")
        return local
    except Exception as e:
        logger.log(f"   ERROR: {e}")
        return None

# ── Blocking runners (used sequentially) ─────────────────────────────────────
def _run_window_block(logger, label: str, cmd: list, cwd=None):
    logger.log(f"\n>> {label}")
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd) if cwd else str(TEMP_DIR),
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        proc.wait()
        if proc.returncode == 0:
            logger.log(f"OK  {label} — done.")
        else:
            logger.log(f"XX  {label} — exit code {proc.returncode}")
    except Exception as e:
        logger.log(f"XX  {e}")

def _do_ps1(logger, label, repo_path, wait_children=False):
    local = gh_download(logger, repo_path)
    if local:
        if wait_children:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0
            ps_cmd = (
                f"Start-Process powershell.exe "
                f"-ArgumentList '-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File','{str(local)}'"
                f" -Wait"
            )
            logger.log(f"\n>> {label}")
            try:
                proc = subprocess.Popen(
                    ["powershell.exe", "-ExecutionPolicy", "Bypass",
                     "-WindowStyle", "Hidden", "-Command", ps_cmd],
                    cwd=str(local.parent),
                    startupinfo=si,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                proc.wait()
                logger.log(f"OK  {label} — done." if proc.returncode == 0
                           else f"XX  {label} — exit code {proc.returncode}")
            except Exception as e:
                logger.log(f"XX  {e}")
        else:
            _run_window_block(logger, label,
                              ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", str(local)],
                              cwd=local.parent)

def _do_bat(logger, label, repo_path):
    local = gh_download(logger, repo_path)
    if local:
        _run_window_block(logger, label, ["cmd.exe", "/c", str(local)], cwd=local.parent)

def _do_reg(logger, label, repo_path):
    local = gh_download(logger, repo_path)
    if local:
        logger.log(f"\n>> Importing registry: {local.name}")
        ret = subprocess.Popen(["reg.exe", "import", str(local)]).wait()
        logger.log(f"OK  Registry imported." if ret == 0 else f"XX  reg import failed (code {ret})")

def _do_ps1_extra(logger, label, ps1_repo, extra_repo):
    local_ps1   = gh_download(logger, ps1_repo)
    local_extra = gh_download(logger, extra_repo)
    if local_ps1 and local_extra:
        _run_window_block(logger, label,
                          ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", str(local_ps1)],
                          cwd=local_ps1.parent)

def _do_open(logger, label, repo_path):
    local = gh_download(logger, repo_path)
    if local:
        try:
            os.startfile(str(local))
            logger.log(f"OK  Opened: {local.name}")
        except Exception as e:
            logger.log(f"XX  {e}")

# ── Async fire-and-forget wrappers ──────────────────
def run_ps1(logger, label, repo_path):
    threading.Thread(target=_do_ps1, args=(logger, label, repo_path), daemon=True).start()

def run_bat(logger, label, repo_path):
    threading.Thread(target=_do_bat, args=(logger, label, repo_path), daemon=True).start()

def run_reg(logger, label, repo_path):
    threading.Thread(target=_do_reg, args=(logger, label, repo_path), daemon=True).start()

def run_ps1_extra(logger, label, ps1_repo, extra_repo):
    threading.Thread(target=_do_ps1_extra, args=(logger, label, ps1_repo, extra_repo), daemon=True).start()

def run_open(logger, label, repo_path):
    threading.Thread(target=_do_open, args=(logger, label, repo_path), daemon=True).start()

# ── PowerShell execution policy check ────────────────────────────────────────
def is_ps_unlocked():
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             "Get-ExecutionPolicy -Scope LocalMachine"],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        policy = result.stdout.strip().lower()
        return policy in ("remotesigned", "unrestricted", "bypass")
    except Exception:
        return False

# ── Sequential runner for Automated tab ──────────────────────────────────────
def run_sequence(logger, tasks: list, done_cb=None):
    def _seq():
        logger.log(f"\n===  Automated: {len(tasks)} task(s) queued  ===")
        for i, task in enumerate(tasks, 1):
            logger.log(f"\n[{i}/{len(tasks)}]")
            task()
        logger.log("\n===  All done  ===")
        if done_cb:
            done_cb()
    threading.Thread(target=_seq, daemon=True).start()

# ── GUI helpers ───────────────────────────────────────────────────────────────
def scrollable(tab):
    tab.columnconfigure(0, weight=1)
    tab.rowconfigure(0, weight=1)
    sf = ctk.CTkScrollableFrame(tab, fg_color="transparent",
                                scrollbar_button_color="#2a2a4a",
                                scrollbar_button_hover_color="#7c86ff")
    sf.grid(row=0, column=0, sticky="nsew")
    sf.columnconfigure(0, weight=1)
    return sf

# ════════════════════════════════════════════════════════════════════════════
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Windows Tweaks GUI  —  kubsonxtm")
        self.iconbitmap(resource_path("rocket.ico"))
        self.geometry("840x600")
        self.minsize(760, 500)
        self.configure(fg_color="#0f0f1a")

        # Header
        hdr = ctk.CTkFrame(self, fg_color="#14142b", corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text="Windows Tweaks GUI",
                     font=ctk.CTkFont(size=19, weight="bold"),
                     text_color="#7c86ff").pack(side="left", padx=16, pady=9)
        ctk.CTkLabel(hdr, text="kubsonxtm/Windows-Tweaks",
                     font=ctk.CTkFont(size=10), text_color="#3a3a5a").pack(side="left")
        adm_txt = "Admin: YES" if is_admin() else "Admin: NO  (click to elevate)"
        adm_col = "#52b788" if is_admin() else "#e63946"
        ctk.CTkButton(hdr, text=adm_txt, fg_color="transparent", text_color=adm_col,
                      hover=False, font=ctk.CTkFont(size=11),
                      command=run_as_admin if not is_admin() else None
                      ).pack(side="right", padx=16)

        # Body
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=10)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        # Left — tabview
        tf = ctk.CTkFrame(body, fg_color="#14142b", corner_radius=10)
        tf.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        tf.columnconfigure(0, weight=1)
        tf.rowconfigure(0, weight=1)
        self.tabview = ctk.CTkTabview(
            tf, fg_color="#14142b",
            segmented_button_fg_color="#1e1e3a",
            segmented_button_selected_color="#7c86ff",
            segmented_button_selected_hover_color="#6370ff",
            segmented_button_unselected_color="#1e1e3a",
            segmented_button_unselected_hover_color="#2a2a4a",
            text_color="#cdd6f4", corner_radius=10,
        )
        self.tabview.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

        # Right — log
        lf = ctk.CTkFrame(body, fg_color="#14142b", corner_radius=10)
        lf.grid(row=0, column=1, sticky="nsew")
        lf.columnconfigure(0, weight=1)
        lf.rowconfigure(1, weight=1)
        ctk.CTkLabel(lf, text="Log", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#7c86ff").grid(row=0, column=0, sticky="w", padx=10, pady=(8, 2))
        self.log_box = ctk.CTkTextbox(lf, fg_color="#0a0a15", text_color="#cdd6f4",
                                      font=ctk.CTkFont(family="Consolas", size=10),
                                      state="disabled", corner_radius=6)
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=7, pady=(0, 4))
        ctk.CTkButton(lf, text="Clear log", height=24, fg_color="#1e1e3a",
                      hover_color="#2a2a4a", text_color="#8ecae6", font=ctk.CTkFont(size=11),
                      command=self._clear_log).grid(row=2, column=0, pady=(0, 7))

        self.logger = Logger(self.log_box)
        self.logger.log("Logs will show there", "ok")

        if is_ps_unlocked():
            self._build_drivers()
            self._build_debloat()
            self._build_tweaks()
            self._build_automated()
            self.tabview.set("Drivers")
            self.logger.log("✔  PowerShell scripts already enabled.", "ok")
        else:
            self._build_start()
            self.tabview.set("Start")
            self.logger.log("⚠  PowerShell scripts not yet enabled.\n   Run 'Enable PowerShell Scripts' first.", "warn")

    # ── shared row builders ───────────────────────────────────────────────
    def _sec(self, p, txt):
        ctk.CTkLabel(p, text=txt, font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#7c86ff").pack(anchor="w", padx=6, pady=(11, 2))

    def _row1(self, p, label, desc, btxt="Run", cmd=None):
        r = ctk.CTkFrame(p, fg_color="#1a1a2e", corner_radius=7)
        r.pack(fill="x", pady=2, padx=4)
        r.columnconfigure(0, weight=1)
        inf = ctk.CTkFrame(r, fg_color="transparent")
        inf.grid(row=0, column=0, sticky="ew", padx=9, pady=7)
        ctk.CTkLabel(inf, text=label, font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#e2e8f0").pack(anchor="w")
        ctk.CTkLabel(inf, text=desc, font=ctk.CTkFont(size=10),
                     text_color="#8892a4", wraplength=360).pack(anchor="w")
        ctk.CTkButton(r, text=btxt, width=105, height=26,
                      fg_color="#7c86ff", hover_color="#6370ff",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      command=cmd).grid(row=0, column=1, padx=9, pady=7, sticky="e")

    def _clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    # ════════════════════════════════════════════════════════════════════
    # Start
    # ════════════════════════════════════════════════════════════════════
    def _build_start(self):
        sf = scrollable(self.tabview.add("Start"))
        ctk.CTkLabel(sf,
                     text="PowerShell scripts are currently DISABLED on this system.\n"
                          "Click Run below to enable them — other tabs will appear automatically.",
                     font=ctk.CTkFont(size=10), text_color="#8892a4",
                     wraplength=360, justify="left").pack(anchor="w", padx=6, pady=(0, 6))

        r = ctk.CTkFrame(sf, fg_color="#1a1a2e", corner_radius=7)
        r.pack(fill="x", pady=2, padx=4)
        r.columnconfigure(0, weight=1)
        inf = ctk.CTkFrame(r, fg_color="transparent")
        inf.grid(row=0, column=0, sticky="ew", padx=9, pady=7)
        ctk.CTkLabel(inf, text="Enable PowerShell Scripts",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#e2e8f0").pack(anchor="w")
        ctk.CTkLabel(inf, text="Unlocks PS execution policy\n1 Enable powershell scripts.cmd",
                     font=ctk.CTkFont(size=10), text_color="#8892a4",
                     wraplength=360).pack(anchor="w")
        run_btn = ctk.CTkButton(r, text="Run", width=105, height=26,
                                fg_color="#7c86ff", hover_color="#6370ff",
                                font=ctk.CTkFont(size=11, weight="bold"),
                                command=lambda: self._run_enable_ps(run_btn))
        run_btn.grid(row=0, column=1, padx=9, pady=7, sticky="e")

    def _run_enable_ps(self, btn):
        btn.configure(state="disabled", text="Running…")
        def _task():
            _do_bat(self.logger, "Enable PS", "1 Enable powershell scripts.cmd")
            if is_ps_unlocked():
                self.after(0, self._unlock_all_tabs)
            else:
                self.after(0, lambda: btn.configure(state="normal", text="Run"))
        threading.Thread(target=_task, daemon=True).start()

    def _unlock_all_tabs(self):
        self.logger.log("\u2714  PowerShell enabled — loading all tabs…", "ok")
        self._build_drivers()
        self._build_debloat()
        self._build_tweaks()
        self._build_automated()
        self.tabview.set("Drivers")
        try:
            self.tabview.delete("Start")
        except Exception:
            pass

    # ════════════════════════════════════════════════════════════════════
    # Drivers
    # ════════════════════════════════════════════════════════════════════
    def _build_drivers(self):
        sf = scrollable(self.tabview.add("Drivers"))
        self._sec(sf, "System Libraries")
        self._row1(sf, "C++ Redistributables",
                   "Microsoft Visual C++ Redistributable\n2 Drivers/C++.ps1",
                   "Run", lambda: run_ps1(self.logger, "C++ Redist", "2 Drivers/C++.ps1"))
        self._row1(sf, "DirectX",
                   "DirectX Runtime install / update\n2 Drivers/DirectX.ps1\n⚠ Requires manual interaction",
                   "Run", lambda: run_ps1(self.logger, "DirectX", "2 Drivers/DirectX.ps1"))

    # ════════════════════════════════════════════════════════════════════
    # Debloat
    # ════════════════════════════════════════════════════════════════════
    def _build_debloat(self):
        sf = scrollable(self.tabview.add("Debloat"))
        self._sec(sf, "Debloat Windows Apps")
        self._row1(sf, "Debloat — All",
                   "Removes ALL default Windows bloatware",
                   "Run",
                   lambda: run_ps1(self.logger, "Debloat All",
                       "3 Automation/Debloat Windows Apps/Debloat (all)/Debloat all Windows Apps.ps1"))
        self._row1(sf, "Debloat — Keep Daily",
                   "Removes bloat but keeps useful everyday apps",
                   "Run",
                   lambda: run_ps1(self.logger, "Debloat Keep",
                       "3 Automation/Debloat Windows Apps/Debloat (keep some apps)/Debloat Windows Apps but keep daily use.ps1"))

    # ════════════════════════════════════════════════════════════════════
    # Tweaks
    # ════════════════════════════════════════════════════════════════════
    def _build_tweaks(self):
        sf = scrollable(self.tabview.add("Tweaks"))

        self._sec(sf, "1 · Chris Titus Tool")
        self._row1(sf, "Chris Titus Tool",
                   "Runs cttautoconfig.ps1 from GitHub\n ⚠ Requires manual interaction",
                   "Run",
                   lambda: run_ps1(self.logger, "CTT",
                                   f"{PRG}/1 CTT/cttautoconfig.ps1"))

        self._sec(sf, "2 · Power Plan")
        self._row1(sf, "Apply Power Plan",
                   "Imports optimised power plan\n2 Powerplan/Power plan.ps1",
                   "Run",
                   lambda: run_ps1(self.logger, "Power Plan",
                                   f"{PRG}/2 Powerplan/Power plan.ps1"))

        self._sec(sf, "3 · Registry")
        self._row1(sf, "Import Registry Tweaks",
                   "Applies registry tweaks\n3 Registry/Registry.reg",
                   "Run",
                   lambda: run_reg(self.logger, "Registry",
                                   f"{PRG}/3 Registry/Registry.reg"))

        self._sec(sf, "4 · O&O ShutUp10++")
        self._row1(sf, "O&O ShutUp10++",
                   "Runs O&O ShutUp.ps1 + imports settings.cfg",
                   "Run",
                   lambda: run_ps1_extra(self.logger, "O&O ShutUp",
                       f"{PRG}/4 O&O Shutup/O&O ShutUp.ps1",
                       f"{PRG}/4 O&O Shutup/O&O ShutUp settings.cfg"))

        self._sec(sf, "5 · Winaero Tweaker")
        self._row1(sf, "Winaero Tweaker",
                   "Runs Winaero.ps1 + imports Winaero Tweaker settings.ini",
                   "Run",
                   lambda: run_ps1(self.logger, "Winaero Tweaker",
                       f"{PRG}/5 Winaero Tweaker/Winaero.ps1"))

        self._sec(sf, "6 · Ultimate Windows Tweaker")
        self._row1(sf, "Ultimate Windows Tweaker",
                   "Runs UWT.ps1 + imports uwt_33557.ini",
                   "Run",
                   lambda: run_ps1(self.logger, "Ultimate Windows Tweaker",
                       f"{PRG}/6 Ultimate Windows Tweaker/UWT.ps1"))

        ctk.CTkLabel(sf, text="", height=14).pack()

    # ════════════════════════════════════════════════════════════════════
    # Automated
    # ════════════════════════════════════════════════════════════════════
    def _build_automated(self):
        tab = self.tabview.add("Automated")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)

        wrap = ctk.CTkFrame(tab, fg_color="transparent")
        wrap.grid(row=0, column=0, sticky="nsew")
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(0, weight=1)

        sf = ctk.CTkScrollableFrame(wrap, fg_color="transparent",
                                    scrollbar_button_color="#2a2a4a",
                                    scrollbar_button_hover_color="#7c86ff")
        sf.grid(row=0, column=0, sticky="nsew")
        sf.columnconfigure(0, weight=1)

        # ── top bar: label + Check All button ────────────────────────────
        top_bar = ctk.CTkFrame(sf, fg_color="transparent")
        top_bar.pack(fill="x", padx=4, pady=(6, 2))
        ctk.CTkLabel(top_bar, text="Check items to include — tasks run one by one in order.",
                     font=ctk.CTkFont(size=10), text_color="#8892a4").pack(side="left", padx=2)
        self._check_all_state = False
        self._check_all_btn = ctk.CTkButton(
            top_bar, text="Check All", width=80, height=22,
            fg_color="#1e1e3a", hover_color="#2a2a4a",
            text_color="#8ecae6", font=ctk.CTkFont(size=10),
            command=self._toggle_check_all,
        )
        self._check_all_btn.pack(side="right", padx=2)

        self._av = {}

        def sec(txt):
            ctk.CTkLabel(sf, text=txt, font=ctk.CTkFont(size=12, weight="bold"),
                         text_color="#7c86ff").pack(anchor="w", padx=6, pady=(11, 2))

        def chk(key, label, desc, on_toggle=None):
            var = ctk.BooleanVar(value=False)
            self._av[key] = var
            r = ctk.CTkFrame(sf, fg_color="#1a1a2e", corner_radius=7)
            r.pack(fill="x", pady=2, padx=4)
            cb = ctk.CTkCheckBox(r, text="", variable=var, width=22,
                            checkbox_width=16, checkbox_height=16,
                            fg_color="#7c86ff", hover_color="#6370ff",
                            border_color="#3a3a5a",
                            command=on_toggle)
            cb.pack(side="left", padx=(9, 3), pady=7)
            inf = ctk.CTkFrame(r, fg_color="transparent")
            inf.pack(side="left", fill="both", expand=True, pady=7)
            ctk.CTkLabel(inf, text=label, font=ctk.CTkFont(size=12, weight="bold"),
                         text_color="#e2e8f0").pack(anchor="w")
            ctk.CTkLabel(inf, text=desc, font=ctk.CTkFont(size=10),
                         text_color="#8892a4", wraplength=340).pack(anchor="w")
            return cb

        sec("Drivers")
        chk("cpp",      "C++ Redistributables", "2 Drivers/C++.ps1")
        chk("directx",  "DirectX",              "2 Drivers/DirectX.ps1  ⚠ requires manual interaction")

        sec("Debloat")
        def _on_deb_all():
            if self._av["deb_all"].get():
                self._av["deb_keep"].set(False)
        def _on_deb_keep():
            if self._av["deb_keep"].get():
                self._av["deb_all"].set(False)

        chk("deb_all",  "Debloat — All",       "Debloat all Windows Apps.ps1", on_toggle=_on_deb_all)
        chk("deb_keep", "Debloat — Keep Daily", "Debloat Windows Apps but keep daily use.ps1", on_toggle=_on_deb_keep)

        sec("Tweaks")
        chk("ctt",       "Chris Titus Tool",         "cttautoconfig.ps1  ⚠ requires manual interaction")
        chk("powerplan", "Power Plan",                "Power plan.ps1")
        chk("registry",  "Registry Tweaks",           "Registry.reg")
        chk("oo",        "O&O ShutUp10++",            "O&O ShutUp.ps1 + settings.cfg")
        chk("winaero",   "Winaero Tweaker",           "Winaero.ps1 + imports Winaero Tweaker settings.ini")
        chk("uwt",       "Ultimate Windows Tweaker",  "UWT.ps1 + imports uwt_33557.ini")

        ctk.CTkLabel(sf, text="", height=6).pack()

        self._run_btn = ctk.CTkButton(
            wrap, text="▶  Run Selected",
            height=34, font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#7c86ff", hover_color="#6370ff",
            command=self._run_automated,
        )
        self._run_btn.grid(row=1, column=0, sticky="ew", padx=6, pady=(3, 7))

    def _toggle_check_all(self):
        self._check_all_state = not self._check_all_state
        val = self._check_all_state
        for key, var in self._av.items():
            if key == "deb_all":
                var.set(False)
            else:
                var.set(val)
        self._check_all_btn.configure(text="Uncheck All" if val else "Check All")

    def _run_automated(self):
        a = self._av
        tasks = []

        if a["cpp"].get():
            tasks.append(lambda: _do_ps1(self.logger, "C++ Redist", "2 Drivers/C++.ps1"))
        if a["directx"].get():
            tasks.append(lambda: _do_ps1(self.logger, "DirectX", "2 Drivers/DirectX.ps1", wait_children=True))
        if a["deb_all"].get():
            tasks.append(lambda: _do_ps1(self.logger, "Debloat All",
                "3 Automation/Debloat Windows Apps/Debloat (all)/Debloat all Windows Apps.ps1"))
        if a["deb_keep"].get():
            tasks.append(lambda: _do_ps1(self.logger, "Debloat Keep",
                "3 Automation/Debloat Windows Apps/Debloat (keep some apps)/Debloat Windows Apps but keep daily use.ps1"))
        if a["ctt"].get():
            tasks.append(lambda: _do_ps1(self.logger, "CTT", f"{PRG}/1 CTT/cttautoconfig.ps1"))
        if a["powerplan"].get():
            tasks.append(lambda: _do_ps1(self.logger, "Power Plan", f"{PRG}/2 Powerplan/Power plan.ps1"))
        if a["registry"].get():
            tasks.append(lambda: _do_reg(self.logger, "Registry", f"{PRG}/3 Registry/Registry.reg"))
        if a["oo"].get():
            tasks.append(lambda: _do_ps1_extra(self.logger, "O&O ShutUp",
                f"{PRG}/4 O&O Shutup/O&O ShutUp.ps1",
                f"{PRG}/4 O&O Shutup/O&O ShutUp settings.cfg"))
        if a["winaero"].get():
            tasks.append(lambda: _do_ps1(self.logger, "Winaero Tweaker",
                f"{PRG}/5 Winaero Tweaker/Winaero.ps1"))
        if a["uwt"].get():
            tasks.append(lambda: _do_ps1(self.logger, "Ultimate Windows Tweaker",
                f"{PRG}/6 Ultimate Windows Tweaker/UWT.ps1"))

        if not tasks:
            self.logger.log("No tasks selected.")
            return

        self._run_btn.configure(state="disabled", text="Running…")
        run_sequence(self.logger, tasks,
                     done_cb=lambda: self._run_btn.configure(state="normal", text="▶  Run Selected"))


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not is_admin():
        ans = ctypes.windll.user32.MessageBoxW(
            0,
            "Administrator rights required.\nRelaunch as Administrator?",
            "Windows Tweaks GUI", 4,
        )
        if ans == 6:
            run_as_admin()
    else:
        app = App()
        app.mainloop()
