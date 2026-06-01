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
            "local_inference": True,       # OpenAI-compatible: any OS with a local server
            "security_sentinel": True,     # behavioral fingerprint, all platforms
            "pc_foreground_tracker": is_windows(),
            "global_hotkey": is_windows(),
            "native_toast": is_windows(),
            "ui_hands": True,
            "macro_recording": is_windows(),
        },
        "notes": [
            "Pip's brain, dashboard, local inference, sentinel, token guard, and recipes run on Windows, macOS, Linux, and Android/Termux.",
            "Local inference is backend-agnostic (llama.cpp, LM Studio, Jan, Ollama) over an OpenAI-compatible /v1 API.",
            "On Android, install_termux.sh runs the whole brain on-device, offline.",
            "Foreground app tracking, global hotkeys, and native toasts are Windows-only until per-OS adapters are added; everything else degrades gracefully.",
        ],
    }
