"""
pip_hands.py - UI automation module for Pip.

Handles typing, clicking, clipboard, and macro recording.
PyAutoGUI works on Windows/macOS/Linux with the right display permissions.
Clipboard uses tkinter (stdlib) so it works everywhere without extra installs.
Macro recording is Windows-only via the keyboard library.
"""
from __future__ import annotations

import time

from . import pip_platform


def _load_pyautogui():
    import pyautogui

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.1
    return pyautogui


# ---------------------------------------------------------------------------
# Typing & clicking
# ---------------------------------------------------------------------------

def type_text(text: str, interval: float = 0.05) -> bool:
    """Type text out like a human."""
    try:
        pyautogui = _load_pyautogui()
        pyautogui.write(text, interval=interval)
        return True
    except Exception as e:
        print(f"[pip] Error typing: {e}")
        return False


def press_key(key: str) -> bool:
    """Press a specific key, such as enter, tab, or esc."""
    try:
        pyautogui = _load_pyautogui()
        pyautogui.press(key)
        return True
    except Exception as e:
        print(f"[pip] Error pressing key: {e}")
        return False


def hotkey(*keys: str) -> bool:
    """Press a key combination (e.g. 'ctrl', 'a')."""
    try:
        pyautogui = _load_pyautogui()
        pyautogui.hotkey(*keys)
        return True
    except Exception as e:
        print(f"[pip] Error pressing hotkey: {e}")
        return False


def click_mouse(x: int | None = None, y: int | None = None) -> bool:
    """Click at the current position or at specific coordinates."""
    try:
        pyautogui = _load_pyautogui()
        if x is not None and y is not None:
            pyautogui.click(x=x, y=y)
        else:
            pyautogui.click()
        return True
    except Exception as e:
        print(f"[pip] Error clicking: {e}")
        return False


# ---------------------------------------------------------------------------
# Clipboard (uses tkinter — no extra installs needed)
# ---------------------------------------------------------------------------

def read_clipboard() -> str:
    """Read current clipboard text. Works on all platforms."""
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        try:
            text = root.clipboard_get()
        except tk.TclError:
            text = ""
        root.destroy()
        return text
    except Exception:
        return ""


def write_clipboard(text: str) -> bool:
    """Write text to the clipboard. Works on all platforms."""
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        root.destroy()
        return True
    except Exception:
        return False


def select_all_and_copy() -> str:
    """Select all content in the focused window and copy to clipboard."""
    try:
        pyautogui = _load_pyautogui()
        if pip_platform.is_macos():
            pyautogui.hotkey("command", "a")
            time.sleep(0.2)
            pyautogui.hotkey("command", "c")
        else:
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.2)
            pyautogui.hotkey("ctrl", "c")
        time.sleep(0.3)
        return read_clipboard()
    except Exception as e:
        print(f"[pip] Error selecting/copying: {e}")
        return read_clipboard()


# ---------------------------------------------------------------------------
# Macro record & playback (Windows-only)
# ---------------------------------------------------------------------------

def record_macro(stop_key: str = "esc") -> list:
    """Record keystrokes until stop_key is pressed."""
    if not pip_platform.is_windows():
        print("[pip] Macro recording is currently Windows-only.")
        return []

    print(f"[pip] Recording macro until '{stop_key}' is pressed...")
    try:
        import keyboard

        recorded = keyboard.record(until=stop_key)
        events = []
        for event in recorded:
            events.append(
                {
                    "event_type": event.event_type,
                    "name": event.name,
                    "time": event.time,
                    "scan_code": getattr(event, "scan_code", 0),
                }
            )
        print(f"[pip] Recorded {len(events)} events.")
        return events
    except Exception as e:
        print(f"[pip] Error recording macro: {e}")
        return []


def play_macro(events: list) -> bool:
    """Play back recorded keyboard events."""
    if not pip_platform.is_windows():
        print("[pip] Macro playback is currently Windows-only.")
        return False

    try:
        import keyboard

        original_events = [
            keyboard.KeyboardEvent(e["event_type"], e.get("scan_code", 0), e["name"], e["time"])
            for e in events
        ]
        keyboard.play(original_events)
        return True
    except Exception as e:
        print(f"[pip] Error playing macro: {e}")
        return False
