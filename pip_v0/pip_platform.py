#!/usr/bin/env python3
from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
BRAIN_ROOT = Path(os.environ.get("PIP_BRAIN_ROOT", ROOT.parent)).expanduser().resolve()


def system_name() -> str:
    return platform.system().lower()


def is_windows() -> bool:
    return system_name() == "windows"


def is_macos() -> bool:
    return system_name() == "darwin"


def is_linux() -> bool:
    return system_name() == "linux"


def hidden_subprocess_kwargs() -> dict[str, Any]:
    if is_windows():
        return {"creationflags": 0x08000000}
    return {}


def popen_hidden_kwargs(**extra: Any) -> dict[str, Any]:
    kwargs = hidden_subprocess_kwargs()
    kwargs.update(extra)
    return kwargs


def feature_status() -> dict[str, Any]:
    return {
        "os": platform.system() or "Unknown",
        "platform": platform.platform(),
        "brain_root": str(BRAIN_ROOT),
        "pip_root": str(ROOT),
        "features": {
            "control_panel": True,
            "workspace_drafts": True,
            "token_governor": True,
            "signal_sieve_bridge": True,
            "blender_recipes": True,
            "hardware_scan": True,
            "installed_app_scan": True,
            "pc_foreground_tracker": is_windows(),
            "global_hotkey": is_windows(),
            "native_toast": is_windows(),
            "ui_hands": True,
            "macro_recording": is_windows(),
        },
        "notes": [
            "Windows has the fullest body layer today.",
            "macOS/Linux should run Pip's brain, dashboard, drafts, token guard, and recipes.",
            "Foreground app tracking and global hotkeys are Windows-only until platform-specific adapters are added.",
        ],
    }
