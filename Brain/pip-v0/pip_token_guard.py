#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pip_config
import pip_platform


ROOT = Path(__file__).resolve().parent
BRAIN_ROOT = pip_platform.BRAIN_ROOT
SIGNAL_SIEVE_DIR = BRAIN_ROOT / "signal" / "signal-sieve"
TOKEN_GOVERNOR_SOURCE = BRAIN_ROOT / "token governor" / "token_governor_system_v0_5_0.tar.gz"

ACTION_MAPPING = {
    "verify_primary": {"priority": "CRITICAL", "max_output_tokens": 700, "energy": "full"},
    "treat_as_lead": {"priority": "NORMAL", "max_output_tokens": 500, "energy": "normal"},
    "seek_receipts": {"priority": "NORMAL", "max_output_tokens": 350, "energy": "careful"},
    "treat_as_background": {"priority": "BACKGROUND", "max_output_tokens": 220, "energy": "brief"},
    "drop": {"priority": "SPECULATIVE", "max_output_tokens": 80, "energy": "tiny"},
    "reject": {"priority": "BLOCKED", "max_output_tokens": 0, "energy": "stop"},
}

INTENT_MULTIPLIERS = {
    "chat": 1.0,
    "autonomous_goal": 3.0,
    "ambient_cycle": 2.0,
    "job": 2.5,
    "blender_recipe": 0.8,
    "skill": 1.2,
    "sieve": 0.7,
}

DEFAULT_STATE = {
    "version": 1,
    "day": "",
    "daily_budget_tokens": 60000,
    "daily_used_tokens": 0,
    "daily_saved_tokens": 0,
    "session_used_tokens": 0,
    "session_saved_tokens": 0,
    "events": [],
    "last_assessment": None,
    "user_nudges": [],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def today_key() -> str:
    return utc_now()[:10]


def state_path() -> Path:
    return pip_config.get_memory_path() / "token_governor_state.json"


def estimate_tokens(text: str, max_output_tokens: int = 250) -> int:
    return max(1, len(text or "") // 4) + max(0, int(max_output_tokens))


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(default)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(default)
    merged = dict(default)
    merged.update(data if isinstance(data, dict) else {})
    return merged


def load_state() -> dict[str, Any]:
    state = _read_json(state_path(), DEFAULT_STATE)
    reset_today = False
    if state.get("day") != today_key():
        state["day"] = today_key()
        state["daily_used_tokens"] = 0
        state["daily_saved_tokens"] = 0
        state["events"] = []
        state["user_nudges"] = []
        reset_today = True
    state.setdefault("events", [])
    state.setdefault("user_nudges", [])
    if reset_today:
        save_state(state)
    return state


def save_state(state: dict[str, Any]) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    state["events"] = state.get("events", [])[-200:]
    state["user_nudges"] = state.get("user_nudges", [])[-50:]
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _fallback_sieve(text: str) -> dict[str, Any]:
    lowered = (text or "").lower()
    pressure_hits = sum(
        phrase in lowered
        for phrase in ["urgent", "must", "now", "always", "never", "guaranteed", "secret", "breakthrough"]
    )
    pressure = min(1.0, pressure_hits / 4)
    action = "seek_receipts" if pressure >= 0.5 else "treat_as_lead"
    return {
        "recommended_action": action,
        "triage_summary": "Fallback token guard heuristic used because local Signal Sieve was unavailable.",
        "scores": {"pressure": pressure, "overall_confidence": 0.35, "signal": 0.35, "noise": pressure},
        "flags": [],
        "questions_to_ask": [],
        "capsule": "Fallback sieve: local signal-sieve import unavailable.",
    }


def analyze_signal(text: str, source_type: str = "first_hand", source_name: str = "Pip user interaction") -> dict[str, Any]:
    if SIGNAL_SIEVE_DIR.exists() and str(SIGNAL_SIEVE_DIR) not in sys.path:
        sys.path.insert(0, str(SIGNAL_SIEVE_DIR))
    try:
        from signal_sieve import analyze

        return analyze(text or "", source_type=source_type, source_name=source_name)
    except Exception as exc:
        result = _fallback_sieve(text)
        result["error"] = str(exc)
        return result


def _mode_for_pressure(pressure: float, remaining_ratio: float) -> str:
    if remaining_ratio <= 0.05 or pressure >= 0.85:
        return "SHED"
    if remaining_ratio <= 0.18 or pressure >= 0.65:
        return "DWELL"
    if remaining_ratio <= 0.42 or pressure >= 0.35:
        return "AUDIT"
    return "BUILD"


def _nudge_for(mode: str, action: str, intent: str, estimated: int) -> str:
    if mode == "SHED":
        return "Pip is in SHED mode. Only critical work should continue; compress, pause, or save a draft."
    if mode == "DWELL":
        return "Pip is in DWELL mode. Keep this brief, prefer summaries, and avoid new autonomous branches."
    if action in {"drop", "reject"}:
        return "Signal Sieve found low signal or high pressure. Pip should answer lightly and ask for receipts before expanding."
    if estimated > 4000:
        return "This is a large request. Pip should condense context before spending more tokens."
    if intent == "autonomous_goal":
        return "Autonomous work is higher-cost. Queue approval and keep the first job narrow."
    return "Budget looks healthy. Proceed normally, but keep outputs purposeful."


def assess_interaction(
    text: str,
    intent: str = "chat",
    source_type: str = "first_hand",
    source_name: str = "Pip user interaction",
) -> dict[str, Any]:
    state = load_state()
    sieve = analyze_signal(text, source_type=source_type, source_name=source_name)
    action = sieve.get("recommended_action", "treat_as_lead")
    mapping = ACTION_MAPPING.get(action, ACTION_MAPPING["treat_as_background"])
    multiplier = INTENT_MULTIPLIERS.get(intent, 1.0)
    estimated = int(estimate_tokens(text, mapping["max_output_tokens"]) * multiplier)
    daily_budget = max(1, int(state.get("daily_budget_tokens", DEFAULT_STATE["daily_budget_tokens"])))
    projected_used = int(state.get("daily_used_tokens", 0)) + estimated
    remaining_ratio = max(0.0, 1.0 - (projected_used / daily_budget))
    pressure_score = float((sieve.get("scores") or {}).get("pressure", 0.0))
    budget_pressure = 1.0 - remaining_ratio
    combined_pressure = min(1.0, 0.55 * budget_pressure + 0.45 * pressure_score)
    mode = _mode_for_pressure(combined_pressure, remaining_ratio)

    allowed = True
    reason = "admitted"
    if action == "reject":
        allowed = False
        reason = "signal_sieve_reject"
    elif mode == "SHED" and mapping["priority"] not in {"CRITICAL"}:
        allowed = False
        reason = "budget_shed"
    elif mode == "DWELL" and mapping["priority"] in {"BACKGROUND", "SPECULATIVE"}:
        allowed = False
        reason = "low_priority_under_pressure"

    assessment = {
        "generated_at": utc_now(),
        "allowed": allowed,
        "reason": reason,
        "mode": mode,
        "intent": intent,
        "priority": mapping["priority"],
        "energy": mapping["energy"],
        "recommended_action": action,
        "max_output_tokens": mapping["max_output_tokens"],
        "estimated_tokens": estimated,
        "daily_budget_tokens": daily_budget,
        "daily_used_tokens": state.get("daily_used_tokens", 0),
        "remaining_ratio_after": round(remaining_ratio, 3),
        "pressure": round(combined_pressure, 3),
        "nudge": _nudge_for(mode, action, intent, estimated),
        "signal": {
            "triage_summary": sieve.get("triage_summary", ""),
            "scores": sieve.get("scores", {}),
            "flags": sieve.get("flags", [])[:5],
            "questions_to_ask": sieve.get("questions_to_ask", [])[:5],
            "capsule": sieve.get("capsule", ""),
        },
        "source": {
            "token_governor_package": str(TOKEN_GOVERNOR_SOURCE),
            "signal_sieve_dir": str(SIGNAL_SIEVE_DIR),
        },
    }
    state["last_assessment"] = assessment
    if not allowed or mode in {"DWELL", "SHED"}:
        state.setdefault("user_nudges", []).append({"at": utc_now(), "intent": intent, "nudge": assessment["nudge"]})
    save_state(state)
    return assessment


def record_event(
    intent: str,
    estimated_tokens: int = 0,
    actual_tokens: int | None = None,
    saved_tokens: int = 0,
    note: str = "",
) -> dict[str, Any]:
    state = load_state()
    spent = max(0, int(actual_tokens if actual_tokens is not None else estimated_tokens))
    saved = max(0, int(saved_tokens))
    state["daily_used_tokens"] = max(0, int(state.get("daily_used_tokens", 0)) + spent)
    state["session_used_tokens"] = max(0, int(state.get("session_used_tokens", 0)) + spent)
    state["daily_saved_tokens"] = max(0, int(state.get("daily_saved_tokens", 0)) + saved)
    state["session_saved_tokens"] = max(0, int(state.get("session_saved_tokens", 0)) + saved)
    state.setdefault("events", []).append(
        {
            "at": utc_now(),
            "intent": intent,
            "estimated_tokens": int(estimated_tokens),
            "actual_tokens": spent,
            "saved_tokens": saved,
            "note": note,
        }
    )
    save_state(state)
    return status()


def status() -> dict[str, Any]:
    state = load_state()
    daily_budget = max(1, int(state.get("daily_budget_tokens", DEFAULT_STATE["daily_budget_tokens"])))
    used = int(state.get("daily_used_tokens", 0))
    remaining = max(0, daily_budget - used)
    remaining_ratio = remaining / daily_budget
    pressure = 1.0 - remaining_ratio
    mode = _mode_for_pressure(pressure, remaining_ratio)
    return {
        "generated_at": utc_now(),
        "mode": mode,
        "daily_budget_tokens": daily_budget,
        "daily_used_tokens": used,
        "daily_remaining_tokens": remaining,
        "daily_saved_tokens": state.get("daily_saved_tokens", 0),
        "session_used_tokens": state.get("session_used_tokens", 0),
        "session_saved_tokens": state.get("session_saved_tokens", 0),
        "remaining_ratio": round(remaining_ratio, 3),
        "pressure": round(pressure, 3),
        "last_assessment": state.get("last_assessment"),
        "recent_events": state.get("events", [])[-10:],
        "recent_nudges": state.get("user_nudges", [])[-5:],
        "signal_sieve_available": SIGNAL_SIEVE_DIR.exists(),
        "token_governor_package_present": TOKEN_GOVERNOR_SOURCE.exists(),
    }
