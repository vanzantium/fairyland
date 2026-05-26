"""
pip_fairy_window.py — always-on-top pywebview launcher for Pip the fairy.

Features:
  • Frameless, always-on-top 320×508 window in the bottom-right corner
  • Ctrl+Shift+P global hotkey to show/hide the window
  • Background poller: Windows toast when a new Pip proposal appears
  • Starts pip_control_panel.py as a subprocess and waits for it to be ready

Requirements:
  pip install pywebview
"""

import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

import webview
import pip_platform

def start_ollama_background():
    """Silently spawn ollama serve in the background if it isn't running."""
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **pip_platform.hidden_subprocess_kwargs(),
        )
    except Exception as e:
        print("Failed to start Ollama in background:", e)

try:
    import pip_pc_tracker
    _TRACKER_AVAILABLE = True
except ImportError:
    _TRACKER_AVAILABLE = False

# ── constants ──────────────────────────────────────────────────────────────────
PORT = 8787
BASE_URL = f"http://127.0.0.1:{PORT}"
FAIRY_URL = f"{BASE_URL}/fairy"
POLL_INTERVAL = 300          # seconds between proposal checks
HOTKEY_ID = 1
MOD_CTRL = 0x0002
MOD_SHIFT = 0x0004
VK_P = 0x50
WM_HOTKEY = 0x0312

# ── DPI-aware screen size ──────────────────────────────────────────────────────
def screen_size():
    if not pip_platform.is_windows():
        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            size = (root.winfo_screenwidth(), root.winfo_screenheight())
            root.destroy()
            return size
        except Exception:
            return 1024, 768

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    w = ctypes.windll.user32.GetSystemMetrics(0)
    h = ctypes.windll.user32.GetSystemMetrics(1)
    return w, h


# ── Windows toast notification ─────────────────────────────────────────────────
def toast(title: str, msg: str) -> None:
    if not pip_platform.is_windows():
        print(f"[pip notification] {title}: {msg}")
        return

    script = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "$n=New-Object System.Windows.Forms.NotifyIcon;"
        "$n.Icon=[System.Drawing.SystemIcons]::Information;"
        "$n.Visible=$true;"
        f"$n.ShowBalloonTip(4000,'{title}','{msg}',"
        "[System.Windows.Forms.ToolTipIcon]::None);"
        "Start-Sleep 5;$n.Dispose()"
    )
    subprocess.Popen(
        ["powershell", "-WindowStyle", "Hidden", "-Command", script],
        **pip_platform.hidden_subprocess_kwargs(),
    )


# ── start the control-panel server ────────────────────────────────────────────
def start_server() -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, "pip_control_panel.py"],
        cwd=str(Path(__file__).resolve().parent),
    )
    # poll until the server accepts connections (up to 12 s)
    for _ in range(24):
        try:
            urllib.request.urlopen(BASE_URL, timeout=1)
            return proc
        except Exception:
            time.sleep(0.5)
    return proc     # return even if still warming up


# ── js_api exposed to the webview page ────────────────────────────────────────
class PipAPI:
    def __init__(self):
        self._window = None

    def set_window(self, w):
        self._window = w

    def hide_window(self):
        if self._window:
            self._window.hide()

    def open_panel(self):
        if self._window:
            self._window.load_url(BASE_URL)


# ── global hotkey thread (Ctrl+Shift+P) ───────────────────────────────────────
def hotkey_thread(window):
    if not pip_platform.is_windows():
        print("[pip] Global hotkey is currently Windows-only.")
        return

    user32 = ctypes.windll.user32
    ok = user32.RegisterHotKey(None, HOTKEY_ID, MOD_CTRL | MOD_SHIFT, VK_P)
    if not ok:
        print("[pip] Could not register Ctrl+Shift+P hotkey (already in use?)")
        return

    msg = wt.MSG()
    while True:
        ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
        if ret == 0 or ret == -1:
            break
        if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
            # toggle visibility — webview API must be called from the main thread
            # use evaluate_js as a bridge since it queues safely
            try:
                window.evaluate_js(
                    "if(document.body){"
                    "  if(window._pipHidden){"
                    "    window.pywebview.api.hide_window.__self__.set_window(window.pywebview.api.hide_window.__self__._window);"
                    "  }"
                    "}"
                )
            except Exception:
                pass
            # direct toggle via Python API
            _toggle_visibility(window)

    user32.UnregisterHotKey(None, HOTKEY_ID)


_hidden = False

def _toggle_visibility(window):
    global _hidden
    _hidden = not _hidden
    if _hidden:
        window.hide()
    else:
        window.show()


# ── proposal poller ────────────────────────────────────────────────────────────
def notification_thread(window):
    global _hidden
    last_seen = None
    time.sleep(10)      # let the server fully start
    while True:
        try:
            with urllib.request.urlopen(f"{BASE_URL}/pip/latest", timeout=4) as r:
                import json
                data = json.loads(r.read())
            proposal = data.get("proposal", "")
            if proposal and proposal != last_seen:
                last_seen = proposal
                short = proposal[:80] + ("…" if len(proposal) > 80 else "")
                toast("Pip has a thought", short)
                if _hidden:
                    window.show()
                    _hidden = False
        except Exception:
            pass
        time.sleep(POLL_INTERVAL)


# ── main ───────────────────────────────────────────────────────────────────────
def main():
    start_ollama_background()
    print("[pip] Starting control panel server…")
    server_proc = start_server()

    sw, sh = screen_size()
    win_w, win_h = 320, 508
    x = sw - win_w - 18
    y = sh - win_h - 52    # above the taskbar

    api = PipAPI()

    window = webview.create_window(
        title="Pip",
        url=FAIRY_URL,
        width=win_w,
        height=win_h,
        x=x,
        y=y,
        frameless=True,
        on_top=True,
        js_api=api,
        background_color="#f0ede0",
        min_size=(win_w, win_h),
        resizable=False,
    )

    api.set_window(window)

    if _TRACKER_AVAILABLE:
        pip_pc_tracker.start()
        print("[pip] PC usage tracker started")

    nightwatch_proc = None
    if os.environ.get("PIP_ENABLE_NIGHTWATCH") == "1":
        print("[pip] Starting Nightwatch background loop...")
        try:
            nightwatch_proc = subprocess.Popen(
                [sys.executable, "pip_nightwatch_loop.py"],
                cwd=str(Path(__file__).resolve().parent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **pip_platform.hidden_subprocess_kwargs(),
            )
        except Exception as e:
            print("[pip] Failed to start Nightwatch:", e)
    else:
        print("[pip] Nightwatch is off. Set PIP_ENABLE_NIGHTWATCH=1 to opt in.")

    def on_loaded():
        threading.Thread(target=hotkey_thread, args=(window,), daemon=True).start()
        threading.Thread(target=notification_thread, args=(window,), daemon=True).start()

    window.events.loaded += on_loaded

    try:
        webview.start(debug=False)
    finally:
        server_proc.terminate()
        if nightwatch_proc:
            try:
                nightwatch_proc.terminate()
            except Exception:
                pass


if __name__ == "__main__":
    main()
