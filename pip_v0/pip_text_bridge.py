"""
pip_text_bridge.py — Clipboard-based text bridge for tool interaction.

Pip types into external tools (Claude Code, Codex, etc.) and harvests
their responses via clipboard. No API keys, no token spend — she just
uses whatever is already open on the screen.

Flow:
  1. Save clipboard (pre-state)
  2. Focus the tool window
  3. Type the task
  4. Press Enter
  5. Wait for the tool to respond
  6. Select all + copy in that window
  7. Read clipboard (post-state)
  8. Extract the new response
  9. Return to Pip
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from . import pip_hands
from . import pip_platform


@dataclass
class BridgeResult:
    ok: bool
    persona: str
    task: str
    response: str = ""
    elapsed_s: float = 0.0
    harvest_method: str = "auto"
    needs_manual_copy: bool = False
    error: str = ""


@dataclass
class BridgeSession:
    persona_name: str
    config: dict = field(default_factory=dict)
    active: bool = False
    last_result: Optional[BridgeResult] = None
    history: list = field(default_factory=list)


_sessions: dict[str, BridgeSession] = {}

# How long the history list can grow per session
_MAX_HISTORY = 50


def _focus_window(title: str) -> bool:
    """Try to bring a window to the foreground by title snippet."""
    try:
        import pygetwindow as gw
        windows = gw.getWindowsWithTitle(title)
        if not windows:
            return False
        win = windows[0]
        if win.isMinimized:
            win.restore()
        try:
            win.activate()
        except Exception:
            try:
                import pyautogui
                pyautogui.click(win.left + win.width // 2, win.top + 10)
            except Exception:
                pass
        time.sleep(0.5)
        return True
    except ImportError:
        return False
    except Exception:
        return False


def _load_persona(name: str) -> Optional[dict]:
    """Load a persona config by name or alias."""
    personas_dir = Path(__file__).resolve().parent / "personas"
    if not personas_dir.exists():
        return None
    for pfile in personas_dir.glob("*.json"):
        try:
            config = json.loads(pfile.read_text(encoding="utf-8"))
            names = [config.get("name", "").lower()]
            names.extend(a.lower() for a in config.get("aliases", []))
            if name.lower() in names:
                return config
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_personas() -> list[dict[str, Any]]:
    """List all available personas and their bridge status."""
    personas_dir = Path(__file__).resolve().parent / "personas"
    result = []
    if not personas_dir.exists():
        return result
    for pfile in personas_dir.glob("*.json"):
        try:
            config = json.loads(pfile.read_text(encoding="utf-8"))
            name = config.get("name", pfile.stem).lower()
            session = _sessions.get(name)
            result.append({
                "name": name,
                "app_name": config.get("app_name", name),
                "window_title": config.get("window_title", ""),
                "response_wait_s": config.get("response_wait_s", 20),
                "active": session.active if session else False,
                "history_count": len(session.history) if session else 0,
                "capabilities": config.get("capabilities", []),
            })
        except Exception:
            continue
    return result


def list_sessions() -> dict[str, Any]:
    """Return status of all active bridge sessions."""
    return {
        name: {
            "active": s.active,
            "history_count": len(s.history),
            "last_task": s.history[-1]["task"] if s.history else None,
            "last_ok": s.history[-1]["ok"] if s.history else None,
        }
        for name, s in _sessions.items()
    }


def send(persona_name: str, task_text: str,
         response_wait_s: float | None = None) -> BridgeResult:
    """
    Send a task to an external tool via text bridge.

    Focuses the tool window, types the task, presses Enter,
    waits for the response, and harvests it via clipboard.
    """
    name = persona_name.lower().replace("@", "")
    config = _load_persona(name)

    if not config:
        return BridgeResult(
            ok=False, persona=name, task=task_text,
            error=f"Unknown persona: {persona_name}",
        )

    window_title = config.get("window_title", "")
    wait_s = response_wait_s if response_wait_s is not None else config.get("response_wait_s", 20)

    if name not in _sessions:
        _sessions[name] = BridgeSession(persona_name=name, config=config)
    session = _sessions[name]
    session.active = True

    start = time.time()

    # 1. Save current clipboard
    pre_clip = pip_hands.read_clipboard()

    # 2. Focus the tool window
    if window_title:
        focused = _focus_window(window_title)
        if not focused:
            result = BridgeResult(
                ok=False, persona=name, task=task_text,
                error=f"Could not find window: {window_title}. Is {config.get('app_name', name)} open?",
            )
            session.last_result = result
            session.active = False
            return result

    # 3. Type the task
    pip_hands.type_text(task_text, interval=0.02)
    time.sleep(0.3)

    # 4. Press Enter
    pip_hands.press_key("enter")

    # 5. Wait for response
    time.sleep(wait_s)

    # 6. Harvest via clipboard — select all in the tool window and copy
    post_clip = pip_hands.select_all_and_copy()
    elapsed = time.time() - start

    # 7. Try to extract just the new content
    response = _extract_new_content(pre_clip, post_clip)
    got_response = bool(response.strip())

    result = BridgeResult(
        ok=True, persona=name, task=task_text,
        response=response if got_response else "",
        elapsed_s=round(elapsed, 1),
        harvest_method="clipboard_auto",
        needs_manual_copy=not got_response,
    )

    _record(session, task_text, result)
    return result


def send_no_harvest(persona_name: str, task_text: str) -> BridgeResult:
    """
    Send a task but don't wait or harvest — just type and go.
    Use harvest_clipboard() later to grab the response.
    """
    name = persona_name.lower().replace("@", "")
    config = _load_persona(name)

    if not config:
        return BridgeResult(
            ok=False, persona=name, task=task_text,
            error=f"Unknown persona: {persona_name}",
        )

    window_title = config.get("window_title", "")

    if name not in _sessions:
        _sessions[name] = BridgeSession(persona_name=name, config=config)
    session = _sessions[name]
    session.active = True

    start = time.time()

    if window_title:
        focused = _focus_window(window_title)
        if not focused:
            result = BridgeResult(
                ok=False, persona=name, task=task_text,
                error=f"Could not find window: {window_title}. Is {config.get('app_name', name)} open?",
            )
            session.last_result = result
            session.active = False
            return result

    pip_hands.type_text(task_text, interval=0.02)
    time.sleep(0.3)
    pip_hands.press_key("enter")

    result = BridgeResult(
        ok=True, persona=name, task=task_text,
        elapsed_s=round(time.time() - start, 1),
        harvest_method="pending",
        needs_manual_copy=True,
    )

    _record(session, task_text, result)
    return result


def harvest_clipboard(persona_name: str = "") -> BridgeResult:
    """
    Manual harvest — read whatever is on the clipboard right now
    and attach it to the last bridge session.

    Call this after the tool finishes and you've copied the response
    (or Pip can try select_all_and_copy on the active window).
    """
    text = pip_hands.read_clipboard()
    name = persona_name.lower().replace("@", "") if persona_name else ""

    if name and name in _sessions:
        session = _sessions[name]
        if session.last_result:
            session.last_result.response = text
            session.last_result.needs_manual_copy = False
            session.last_result.harvest_method = "clipboard_manual"
            session.active = False
            return session.last_result

    return BridgeResult(
        ok=bool(text), persona=name or "(unknown)",
        task="(manual harvest)",
        response=text, harvest_method="clipboard_manual",
    )


def harvest_active_window(persona_name: str = "") -> BridgeResult:
    """
    Focus the persona's window, select all, copy, and return the content.
    """
    name = persona_name.lower().replace("@", "") if persona_name else ""
    config = _load_persona(name) if name else None

    if config and config.get("window_title"):
        _focus_window(config["window_title"])
        time.sleep(0.3)

    text = pip_hands.select_all_and_copy()

    if name and name in _sessions:
        session = _sessions[name]
        if session.last_result:
            session.last_result.response = text
            session.last_result.needs_manual_copy = False
            session.last_result.harvest_method = "window_harvest"
            session.active = False
            return session.last_result

    return BridgeResult(
        ok=bool(text), persona=name or "(active window)",
        task="(window harvest)",
        response=text, harvest_method="window_harvest",
    )


def get_last_result(persona_name: str) -> Optional[BridgeResult]:
    """Get the last bridge result for a persona."""
    name = persona_name.lower().replace("@", "")
    session = _sessions.get(name)
    if session and session.last_result:
        return session.last_result
    return None


def get_history(persona_name: str) -> list[dict]:
    """Get task history for a persona."""
    name = persona_name.lower().replace("@", "")
    session = _sessions.get(name)
    if session:
        return list(session.history)
    return []


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _extract_new_content(pre: str, post: str) -> str:
    """Try to isolate just the new content from a clipboard diff."""
    if not post:
        return ""
    if not pre:
        return post
    if post == pre:
        return ""
    if post.startswith(pre):
        return post[len(pre):].strip()
    if pre in post:
        idx = post.rfind(pre)
        return post[idx + len(pre):].strip()
    return post


def _record(session: BridgeSession, task: str, result: BridgeResult) -> None:
    session.last_result = result
    session.history.append({
        "task": task,
        "response_length": len(result.response),
        "elapsed_s": result.elapsed_s,
        "ok": result.ok,
        "harvest_method": result.harvest_method,
    })
    if len(session.history) > _MAX_HISTORY:
        session.history = session.history[-_MAX_HISTORY:]
    session.active = False
