"""
Bridge — connects PipV0's weekly compression to Fairyland's real-time loop.

PipV0 is the slow body: weekly usage telemetry -> friction detection -> proposal.
Fairyland is the fast nervous system: tick-by-tick pressure, breath, healing.

This bridge:
  1. Feeds PipV0's ThermalState into Fairyland's KernelState on session start
  2. Feeds Fairyland's friction logs back into PipV0's weekly cycle
  3. Connects tiered memory (fur/skin/tattoo) to both systems
  4. Applies the Token Governor's budget awareness to Fairyland's reveal speed
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from fairyland.engine.state import KernelState, Mode
from fairyland.memory.tiered import (
    TieredMemoryState,
    compute_kernel_adjustments,
    decay_tiered_memory,
    record_feedback,
    update_tattoos,
)


# ---------------------------------------------------------------------------
# PipV0 ThermalState -> Fairyland KernelState
# ---------------------------------------------------------------------------

@dataclass
class PipThermal:
    """PipV0's weekly thermal state (from pip_engine.derive_thermal_state)."""
    coherence: float = 0.5
    pressure: float = 0.0
    drift: float = 0.0
    groove: float = 0.5
    integration_debt: float = 0.0
    scar: float = 0.0


def load_pip_thermal(path: str) -> Optional[PipThermal]:
    """Load the latest PipV0 dream result to get thermal state."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        ts = data.get("thermal_state", {})
        return PipThermal(
            coherence=ts.get("coherence", 0.5),
            pressure=ts.get("pressure", 0.0),
            drift=ts.get("drift", 0.0),
            groove=ts.get("groove", 0.5),
            integration_debt=ts.get("integration_debt", 0.0),
            scar=ts.get("scar", 0.0),
        )
    except (json.JSONDecodeError, KeyError):
        return None


def seed_kernel_from_pip(kernel: KernelState,
                         thermal: PipThermal,
                         tiered: Optional[TieredMemoryState] = None) -> None:
    """
    Seed a Fairyland KernelState from PipV0's weekly thermal state
    and tiered memory adjustments.

    This runs once at session start. It doesn't override — it nudges
    the starting position so the real-time loop begins from a grounded
    baseline rather than zero.
    """
    # thermal influence (dampened — weekly signal shouldn't dominate tick state)
    kernel.coherence = 0.7 * kernel.coherence + 0.3 * thermal.coherence
    kernel.pressure = max(0.0, kernel.pressure + thermal.pressure * 0.15)
    kernel.groove = 0.7 * kernel.groove + 0.3 * thermal.groove
    kernel.debt = max(0.0, min(1.0, kernel.debt + thermal.integration_debt * 0.2))
    kernel.stress = max(0.0, min(1.0, thermal.drift * 0.3))

    # tiered memory adjustments
    if tiered:
        adjustments = compute_kernel_adjustments(tiered)
        kernel.stress = max(0.0, min(1.0,
            kernel.stress + adjustments.get("stress_offset", 0.0)))
        kernel.pressure = max(0.0, min(1.0,
            kernel.pressure + adjustments.get("pressure_baseline", 0.0)))
        kernel.reserve = max(0.0, min(1.0,
            kernel.reserve + adjustments.get("reserve_offset", 0.0)))


# ---------------------------------------------------------------------------
# Fairyland session friction -> PipV0 weekly input
# ---------------------------------------------------------------------------

@dataclass
class SessionFrictionSummary:
    """What a Fairyland session contributes to PipV0's next weekly cycle."""
    session_id: str
    tick_count: int
    avg_pressure: float
    max_pressure: float
    dominant_tone: Optional[str]
    hesitation_count: int
    tattoo_produced: Optional[str]
    breath_overdrive_count: int
    drift_scores: Dict[str, float]


def extract_session_friction(session_id: str, engine, memory) -> SessionFrictionSummary:
    """
    Extract a friction summary from a Fairyland session
    for PipV0's weekly compression cycle.
    """
    artifacts = memory.state.daily_artifacts
    if not artifacts:
        return SessionFrictionSummary(
            session_id=session_id,
            tick_count=engine.state.tick,
            avg_pressure=engine.state.kernel.pressure,
            max_pressure=engine.state.kernel.pressure,
            dominant_tone=None,
            hesitation_count=0,
            tattoo_produced=None,
            breath_overdrive_count=0,
            drift_scores={},
        )

    pressures = [a.pressure for a in artifacts]
    from collections import Counter
    tone_counts = Counter(a.tone for a in artifacts if a.tone)
    dominant = tone_counts.most_common(1)[0][0] if tone_counts else None
    hesitations = sum(1 for a in artifacts if a.hesitation != "NONE")

    drift_hud = engine.get_drift_hud() if hasattr(engine, 'get_drift_hud') else {}

    return SessionFrictionSummary(
        session_id=session_id,
        tick_count=engine.state.tick,
        avg_pressure=sum(pressures) / len(pressures),
        max_pressure=max(pressures),
        dominant_tone=dominant,
        hesitation_count=hesitations,
        tattoo_produced=None,
        breath_overdrive_count=0,
        drift_scores=drift_hud,
    )


def friction_to_pip_events(summary: SessionFrictionSummary) -> List[Dict[str, Any]]:
    """
    Convert a Fairyland friction summary into PipV0-compatible usage events.

    This lets PipV0's weekly engine process Fairyland sessions alongside
    phone/PC usage data in the same compression pipeline.
    """
    events = []
    events.append({
        "timestamp": "",
        "app_name": "fairyland_session",
        "event_type": "session",
        "battery_delta": 0,
        "notifications_received": summary.hesitation_count,
        "notifications_dismissed_unread": summary.breath_overdrive_count,
        "session_duration_seconds": max(1, summary.tick_count * 5),
    })
    return events


# ---------------------------------------------------------------------------
# Token Governor -> Fairyland reveal speed
# ---------------------------------------------------------------------------

@dataclass
class GovernorState:
    """Minimal Token Governor state for Fairyland integration."""
    daily_budget: int = 60000
    daily_used: int = 0
    mode: str = "BUILD"   # BUILD / AUDIT / DWELL / SHED

    @property
    def budget_remaining_ratio(self) -> float:
        if self.daily_budget <= 0:
            return 0.0
        return max(0.0, 1.0 - self.daily_used / self.daily_budget)


def load_governor_state(path: str) -> GovernorState:
    """Load Token Governor state from PipV0's state file."""
    p = Path(path)
    if not p.exists():
        return GovernorState()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        budget = data.get("daily_budget_tokens", 60000)
        used = data.get("daily_used_tokens", 0)
        remaining = max(0.0, 1.0 - used / max(budget, 1))

        if remaining > 0.42:
            mode = "BUILD"
        elif remaining > 0.18:
            mode = "AUDIT"
        elif remaining > 0.05:
            mode = "DWELL"
        else:
            mode = "SHED"

        return GovernorState(daily_budget=budget, daily_used=used, mode=mode)
    except (json.JSONDecodeError, KeyError):
        return GovernorState()


def governor_to_reveal_speed(gov: GovernorState) -> float:
    """
    Map Token Governor state to Fairyland's reveal_speed.

    BUILD  -> 0.7 (full reveal)
    AUDIT  -> 0.5 (summarize)
    DWELL  -> 0.3 (minimal)
    SHED   -> 0.1 (nearly silent)
    """
    return {
        "BUILD": 0.7,
        "AUDIT": 0.5,
        "DWELL": 0.3,
        "SHED": 0.1,
    }.get(gov.mode, 0.5)


# ---------------------------------------------------------------------------
# Tiered memory persistence (JSON file, same format as PipV0)
# ---------------------------------------------------------------------------

def load_tiered_memory(path: str) -> TieredMemoryState:
    """Load tiered memory from a JSON file."""
    p = Path(path)
    if not p.exists():
        return TieredMemoryState()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        state = TieredMemoryState(
            tattoo_history=data.get("tattoo_history", {}),
            skin_weights=data.get("skin_weights", {}),
            cooldowns=data.get("cooldowns", {}),
            compost_log=data.get("compost_log", []),
            cycle_count=data.get("cycle_count", 0),
        )
        from fairyland.memory.tiered import FurReaction
        for fr in data.get("fur_reactions", []):
            state.fur_reactions.append(FurReaction(
                key=fr.get("key", ""),
                effect=fr.get("effect", ""),
                strength=fr.get("strength", 0.0),
                tone=fr.get("tone"),
            ))
        return state
    except (json.JSONDecodeError, KeyError):
        return TieredMemoryState()


def save_tiered_memory(state: TieredMemoryState, path: str) -> None:
    """Save tiered memory to a JSON file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "cycle_count": state.cycle_count,
        "tattoo_history": state.tattoo_history,
        "skin_weights": state.skin_weights,
        "fur_reactions": [
            {"key": f.key, "effect": f.effect, "strength": f.strength, "tone": f.tone}
            for f in state.fur_reactions
        ],
        "cooldowns": state.cooldowns,
        "compost_log": state.compost_log,
    }
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
