"""
pip_personas.py — Persona orchestrator for the Digital Tavern.

Loads persona configs (Claude Code, Codex, Antigravity, etc.) and
dispatches tasks via the text bridge — Pip types into the tool window,
waits for a response, and copies it back through the clipboard.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import pip_evolution
from . import pip_safety
from . import pip_text_bridge

PERSONAS_DIR = Path(__file__).resolve().parent / "personas"


def load_personas() -> dict:
    """Load all available persona configurations."""
    personas = {}
    if not PERSONAS_DIR.exists():
        PERSONAS_DIR.mkdir()
        return personas

    for pfile in PERSONAS_DIR.glob("*.json"):
        try:
            config = json.loads(pfile.read_text(encoding="utf-8"))
            if "name" in config:
                personas[config["name"].lower()] = config
                for alias in config.get("aliases", []):
                    personas[str(alias).lower()] = config
        except Exception as e:
            print(f"[personas] Failed to load {pfile.name}: {e}")

    return personas


def dispatch_task(persona_name: str, task_text: str,
                  approved_request_id: str = "",
                  response_wait_s: float | None = None) -> dict:
    """
    Dispatch a task to a persona via text bridge.

    First call (no approval): queues a safety permission request.
    Second call (with approved_request_id): executes the bridge.
    """
    personas = load_personas()
    name = persona_name.lower().replace("@", "")

    if name not in personas:
        return {
            "ok": False,
            "message": f"Unknown persona: {persona_name}. "
                       f"Available: {', '.join(set(c.get('name','') for c in personas.values()))}",
        }

    config = personas[name]
    app_name = config.get("app_name", name)

    # --- Phase 1: require approval ---
    if not approved_request_id:
        request = pip_safety.request_safety_permission(
            "ui_automation",
            title=f"Approve text bridge: {app_name}",
            rationale=f"Pip will type into {app_name}, wait for a response, and copy it back.",
            details={
                "persona": name,
                "app": app_name,
                "task_preview": task_text[:120],
            },
        )
        return {
            "ok": False,
            "blocked": True,
            "message": f"Queued {app_name} bridge for approval. "
                       f"Approve in the dashboard, then re-send with the request ID.",
            "permission_request": request,
        }

    # --- Phase 2: verify approval and execute ---
    consumed = pip_safety.consume_approved_permission(
        "ui_automation", approved_request_id,
    )
    if not consumed.get("ok"):
        return {
            "ok": False,
            "message": consumed.get("message", "Permission not valid."),
        }

    # Execute via text bridge
    result = pip_text_bridge.send(name, task_text, response_wait_s=response_wait_s)

    if result.ok:
        pip_evolution.award_xp(app_name, 5)

    return {
        "ok": result.ok,
        "persona": result.persona,
        "app": app_name,
        "task": result.task,
        "response": result.response,
        "elapsed_s": result.elapsed_s,
        "harvest_method": result.harvest_method,
        "needs_manual_copy": result.needs_manual_copy,
        "error": result.error or None,
    }


def quick_send(persona_name: str, task_text: str,
               response_wait_s: float | None = None) -> dict:
    """
    Skip the permission queue and send directly.
    Use this when the user is sitting at the keyboard and
    explicitly asked Pip to talk to a tool.
    """
    result = pip_text_bridge.send(
        persona_name, task_text, response_wait_s=response_wait_s,
    )

    if result.ok:
        config = pip_text_bridge._load_persona(persona_name.lower().replace("@", ""))
        app_name = config.get("app_name", persona_name) if config else persona_name
        pip_evolution.award_xp(app_name, 5)

    return {
        "ok": result.ok,
        "persona": result.persona,
        "task": result.task,
        "response": result.response,
        "elapsed_s": result.elapsed_s,
        "harvest_method": result.harvest_method,
        "needs_manual_copy": result.needs_manual_copy,
        "error": result.error or None,
    }
