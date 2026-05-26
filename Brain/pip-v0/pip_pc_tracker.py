"""
pip_pc_tracker.py — foreground-app usage tracker for Windows.

Polls the active window every 5 s, builds sessions ≥ 10 s, exports to
imports/pc_usage_YYYY-MM-DD.json every 30 min, and auto-POSTs to the
Pip control panel (/pc/usage-import) every 2 h so PC behavior stays
separate from S25 phone memory.

Run standalone:  python pip_pc_tracker.py
Or import and call start() in a background thread from pip_fairy_window.py.
"""

import ctypes
import ctypes.wintypes as wt
import datetime
import json
import os
import sys
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

import pip_platform

# ── config ────────────────────────────────────────────────────────────────────
POLL_SECONDS    = 5
MIN_SESSION_SEC = 10
EXPORT_INTERVAL = 1800      # 30 min
POST_INTERVAL   = 7200      # 2 h
PORT            = 8787
IMPORT_DIR      = Path(__file__).parent / "imports"

# ── ctypes helpers ────────────────────────────────────────────────────────────
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ           = 0x0010

def _get_foreground_app() -> str:
    """Return the stem of the foreground process exe, or '' on failure."""
    if not pip_platform.is_windows():
        return ""

    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return ""
        pid = wt.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid.value
        )
        if not handle:
            return ""
        buf = ctypes.create_unicode_buffer(512)
        ctypes.windll.psapi.GetModuleFileNameExW(handle, None, buf, 512)
        ctypes.windll.kernel32.CloseHandle(handle)
        name = buf.value
        return Path(name).stem if name else ""
    except Exception:
        return ""


# ── event builder ─────────────────────────────────────────────────────────────
def _make_event(app: str, duration: int) -> dict:
    return {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "app_name": app,
        "event_type": "ACTIVITY_PAUSED",
        "battery_delta": 0,
        "notifications_received": 0,
        "notifications_dismissed_unread": 0,
        "session_duration_seconds": duration,
    }


# ── export helpers ────────────────────────────────────────────────────────────
def _export(events: list) -> None:
    if not events:
        return
    IMPORT_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    path = IMPORT_DIR / f"pc_usage_{date_str}.json"
    existing = []
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    combined = existing + events
    path.write_text(json.dumps(combined, indent=2), encoding="utf-8")
    print(f"[tracker] exported {len(events)} events → {path.name}")


def _post(events: list) -> None:
    if not events:
        return
    payload = json.dumps(events).encode("utf-8")
    url = f"http://127.0.0.1:{PORT}/pc/usage-import"
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=4) as r:
            print(f"[tracker] posted {len(events)} events → server ({r.status})")
    except urllib.error.URLError:
        pass    # server not running yet — will retry next cycle


# ── main tracking loop ────────────────────────────────────────────────────────
def _run():
    current_app  = ""
    session_start = time.monotonic()
    pending_events: list = []
    last_export   = time.monotonic()
    last_post     = time.monotonic()

    while True:
        time.sleep(POLL_SECONDS)
        app = _get_foreground_app()
        now = time.monotonic()

        if app != current_app:
            duration = int(now - session_start)
            if current_app and duration >= MIN_SESSION_SEC:
                pending_events.append(_make_event(current_app, duration))
            current_app   = app
            session_start = now

        if now - last_export >= EXPORT_INTERVAL:
            _export(pending_events)
            pending_events = []
            last_export = now

        if now - last_post >= POST_INTERVAL:
            _post(pending_events)
            last_post = now


def start():
    """Start the tracker in a daemon thread (called from pip_fairy_window.py)."""
    if not pip_platform.is_windows():
        print("[tracker] PC foreground tracker is currently Windows-only.")
        return None

    t = threading.Thread(target=_run, daemon=True, name="pip-pc-tracker")
    t.start()
    return t


if __name__ == "__main__":
    if not pip_platform.is_windows():
        print("[tracker] PC foreground tracker is currently Windows-only.")
        raise SystemExit(0)

    print("[tracker] PC usage tracker running (Ctrl+C to stop)")
    try:
        _run()
    except KeyboardInterrupt:
        print("[tracker] stopped")
