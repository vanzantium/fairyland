"""
Tiered Memory — fur / skin / tattoo, adapted from PipV0.

Three decay rates for three timescales:
  - Fur: ultra-fast reactions (0.7x per cycle, threshold 0.05)
    Immediate responses to recent friction — what just happened.
  - Skin: slow-decaying biases (0.92x per cycle, threshold 0.01)
    Weekly-scale patterns — what keeps happening.
  - Tattoo: persistent scars (decay -1 recurrence per cycle if signal fades)
    Durable marks — what has been proven through repetition.

Cooldowns prevent the system from re-proposing recently addressed friction.
Compost actively removes stale entries when their signal disappears.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FurReaction:
    """Ultra-fast reaction — decays in 3-4 cycles."""
    key: str
    effect: str        # "cooled", "avoid_repeat", "delay", "resolved"
    strength: float    # decays at 0.7x
    tone: Optional[str] = None

    FUR_DECAY = 0.7
    FUR_THRESHOLD = 0.05


@dataclass
class TieredMemoryState:
    """Three-tier memory inspired by PipV0's biomimetic model."""
    # tattoo: durable scars (key -> recurrence count)
    tattoo_history: Dict[str, int] = field(default_factory=dict)

    # skin: slow-decaying biases (key -> weight, -0.5 to 1.0)
    skin_weights: Dict[str, float] = field(default_factory=dict)

    # fur: ultra-fast reactions
    fur_reactions: List[FurReaction] = field(default_factory=list)

    # cooldowns: soft resets on accepted/resolved friction
    cooldowns: Dict[str, float] = field(default_factory=dict)

    # compost: archived stale entries
    compost_log: List[Dict[str, Any]] = field(default_factory=list)

    # cycle counter
    cycle_count: int = 0


# Decay constants
SKIN_DECAY = 0.92
SKIN_THRESHOLD = 0.01
FUR_DECAY = 0.7
FUR_THRESHOLD = 0.05
COOLDOWN_DECAY = 0.82
COOLDOWN_THRESHOLD = 0.05
MAX_FUR = 12
MAX_COMPOST = 20


def decay_tiered_memory(state: TieredMemoryState) -> None:
    """Apply one cycle of decay across all tiers."""
    # skin decay
    decayed_skin = {}
    for key, value in state.skin_weights.items():
        new_val = round(value * SKIN_DECAY, 3)
        if abs(new_val) >= SKIN_THRESHOLD:
            decayed_skin[key] = new_val
    state.skin_weights = decayed_skin

    # fur decay
    surviving_fur = []
    for fur in state.fur_reactions:
        new_strength = round(fur.strength * FUR_DECAY, 3)
        if new_strength >= FUR_THRESHOLD:
            surviving_fur.append(FurReaction(
                key=fur.key, effect=fur.effect,
                strength=new_strength, tone=fur.tone,
            ))
    state.fur_reactions = surviving_fur[-MAX_FUR:]

    # cooldown decay
    decayed_cooldowns = {}
    for key, value in state.cooldowns.items():
        new_val = round(value * COOLDOWN_DECAY, 3)
        if new_val >= COOLDOWN_THRESHOLD:
            decayed_cooldowns[key] = new_val
    state.cooldowns = decayed_cooldowns


def record_feedback(state: TieredMemoryState, key: str,
                    status: str, tone: Optional[str] = None) -> None:
    """
    Record human feedback into the memory tiers.

    Statuses: accepted, rejected, deferred, resolved
    """
    current_skin = state.skin_weights.get(key, 0.0)

    if status == "accepted":
        state.skin_weights[key] = round(max(-0.5, current_skin - 0.25), 3)
        state.cooldowns[key] = round(
            min(1.0, state.cooldowns.get(key, 0.0) + 0.45), 3)
        state.fur_reactions.append(FurReaction(
            key=key, effect="cooled", strength=0.25, tone=tone))

    elif status == "rejected":
        state.skin_weights[key] = round(min(1.0, current_skin + 0.35), 3)
        state.fur_reactions.append(FurReaction(
            key=key, effect="avoid_repeat", strength=0.35, tone=tone))

    elif status == "deferred":
        state.skin_weights[key] = round(min(1.0, current_skin + 0.12), 3)
        state.fur_reactions.append(FurReaction(
            key=key, effect="delay", strength=0.18, tone=tone))

    elif status == "resolved":
        state.skin_weights[key] = round(max(-0.75, current_skin - 0.4), 3)
        state.cooldowns[key] = round(
            min(1.0, state.cooldowns.get(key, 0.0) + 0.8), 3)
        state.fur_reactions.append(FurReaction(
            key=key, effect="resolved", strength=0.5, tone=tone))
        state.compost_log.append({
            "cycle": state.cycle_count,
            "key": key,
            "reason": "user_resolved",
        })

    state.fur_reactions = state.fur_reactions[-MAX_FUR:]
    state.compost_log = state.compost_log[-MAX_COMPOST:]


def update_tattoos(state: TieredMemoryState,
                   active_keys: set, cycle: int) -> None:
    """
    Update tattoo recurrence counts.

    Active keys get +1. Inactive keys get -1 and are deleted at 0.
    This is PipV0's compost-on-signal-fade mechanic.
    """
    for key in active_keys:
        state.tattoo_history[key] = state.tattoo_history.get(key, 0) + 1
        state.skin_weights[key] = round(
            min(1.0, state.skin_weights.get(key, 0.0) + 0.05), 3)

    stale_keys = []
    for key in list(state.tattoo_history):
        if key not in active_keys:
            state.tattoo_history[key] = max(0, state.tattoo_history[key] - 1)
            if state.tattoo_history[key] == 0:
                stale_keys.append(key)

    for key in stale_keys:
        del state.tattoo_history[key]
        state.skin_weights.pop(key, None)
        state.cooldowns.pop(key, None)
        state.compost_log.append({
            "cycle": cycle,
            "key": key,
            "reason": "signal_faded",
        })
    state.compost_log = state.compost_log[-MAX_COMPOST:]


def compute_kernel_adjustments(state: TieredMemoryState) -> Dict[str, float]:
    """
    Derive kernel adjustments from memory tiers.

    Returns modifiers that should be applied when initializing
    a Fairyland session's KernelState.
    """
    adjustments: Dict[str, float] = {}

    # tattoo depth -> raise or lower initial stress
    if state.tattoo_history:
        avg_recurrence = sum(state.tattoo_history.values()) / len(state.tattoo_history)
        if avg_recurrence > 3:
            adjustments["stress_offset"] = 0.1
        elif avg_recurrence < 1.5:
            adjustments["stress_offset"] = -0.05

    # recent fur reactions -> pressure baseline
    if state.fur_reactions:
        avg_strength = sum(f.strength for f in state.fur_reactions) / len(state.fur_reactions)
        adjustments["pressure_baseline"] = round(avg_strength * 0.15, 3)

    # high cooldowns -> lower initial reserve (system has been working)
    if state.cooldowns:
        max_cooldown = max(state.cooldowns.values())
        if max_cooldown > 0.5:
            adjustments["reserve_offset"] = -0.1

    # scar depth (total tattoo count)
    total_scars = sum(state.tattoo_history.values())
    adjustments["scar_depth"] = min(1.0, total_scars * 0.02)

    return adjustments


def get_fur_penalty(state: TieredMemoryState, key: str) -> float:
    """Get the combined fur penalty for a given friction key."""
    penalty = 0.0
    for fur in state.fur_reactions:
        if fur.key != key:
            continue
        if fur.effect == "avoid_repeat":
            penalty += fur.strength * 0.5
        elif fur.effect == "delay":
            penalty += fur.strength * 0.25
        elif fur.effect == "resolved":
            penalty += fur.strength * 0.4
    return penalty
