"""
pip_hands.py - UI automation module for Pip.

This module is intentionally best-effort across operating systems. PyAutoGUI can
work on Windows/macOS/Linux if the host has the right accessibility/display
permissions, while keyboard macro recording is currently treated as Windows-only.
"""
from __future__ import annotations

import pip_platform


def _load_pyautogui():
    import pyautogui

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.1
    return pyautogui


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
