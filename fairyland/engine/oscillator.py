"""
Oscillator — the engine's macro rhythm.

Drives mode transitions: BUILD -> AUDIT -> DWELL -> SHED -> BUILD
Each mode alters how the engine processes input, how fast information
is revealed, and how aggressively memory decays.

phi accumulates each tick. Mode transitions happen at phase boundaries
(phi crossing 0.25, 0.5, 0.75, 0.0). Pressure and coherence modulate
the rate of phi accumulation — high pressure accelerates toward SHED,
high coherence lets BUILD linger.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .state import KernelState, Mode, OscillatorState

# Phase boundaries: phi ranges for each mode
# BUILD:  0.00 - 0.25  (accumulating, exploring)
# AUDIT:  0.25 - 0.50  (reviewing, narrowing)
# DWELL:  0.50 - 0.75  (compressing, synthesizing)
# SHED:   0.75 - 1.00  (releasing, decaying)

_MODE_BOUNDARIES = {
    Mode.BUILD: (0.00, 0.25),
    Mode.AUDIT: (0.25, 0.50),
    Mode.DWELL: (0.50, 0.75),
    Mode.SHED:  (0.75, 1.00),
}

_MODE_ORDER = [Mode.BUILD, Mode.AUDIT, Mode.DWELL, Mode.SHED]


def _mode_from_phi(phi: float) -> Mode:
    """Determine mode from current phi position."""
    phi = phi % 1.0
    if phi < 0.25:
        return Mode.BUILD
    elif phi < 0.50:
        return Mode.AUDIT
    elif phi < 0.75:
        return Mode.DWELL
    else:
        return Mode.SHED


def advance_oscillator(osc: OscillatorState, kernel: KernelState, tick: int) -> OscillatorState:
    """
    Advance the oscillator one tick.

    Base rate: 0.01 per tick (~100 ticks per full cycle).
    Modulated by:
      - pressure: high pressure accelerates (wants to reach SHED faster)
      - coherence: high coherence decelerates (comfortable, no rush)
      - groove: good groove slows BUILD phase (stay in flow)
    """
    base_rate = 0.01

    # pressure accelerates — system under load wants to shed
    pressure_mod = 1.0 + kernel.pressure * 0.8

    # coherence decelerates — system is stable, no need to rush
    coherence_mod = 1.0 - kernel.coherence * 0.4

    # groove slows during BUILD — we're in a good rhythm, linger
    groove_mod = 1.0
    if osc.mode == Mode.BUILD and kernel.groove > 0.5:
        groove_mod = 0.6

    dphi = base_rate * pressure_mod * max(0.2, coherence_mod) * groove_mod

    old_mode = osc.mode
    new_phi = (osc.phi + dphi) % 1.0
    new_mode = _mode_from_phi(new_phi)

    # determine phase (rising/falling within the mode's quarter)
    lo, hi = _MODE_BOUNDARIES[new_mode]
    midpoint = (lo + hi) / 2.0
    phase = "rising" if new_phi < midpoint else "falling"

    in_dwell = new_mode == Mode.DWELL

    return OscillatorState(
        phi=new_phi,
        mode=new_mode,
        phase=phase,
        in_dwell=in_dwell,
    )


@dataclass
class ModeEffect:
    """How the current oscillator mode modifies engine behavior."""
    pressure_damping: float    # multiplied into pressure (< 1 = calming)
    decay_rate: float          # how fast memory/state decays
    reveal_speed: float        # how much info to show (0=minimal, 1=full)
    input_suppression: float   # how much to suppress new input (DWELL dampens)


def mode_effects(mode: Mode) -> ModeEffect:
    """Return the behavioral modifiers for a given mode."""
    if mode == Mode.BUILD:
        return ModeEffect(
            pressure_damping=1.0,
            decay_rate=0.02,
            reveal_speed=0.7,
            input_suppression=0.0,
        )
    elif mode == Mode.AUDIT:
        return ModeEffect(
            pressure_damping=0.8,
            decay_rate=0.05,
            reveal_speed=0.5,
            input_suppression=0.1,
        )
    elif mode == Mode.DWELL:
        return ModeEffect(
            pressure_damping=0.5,
            decay_rate=0.1,
            reveal_speed=0.3,
            input_suppression=0.4,
        )
    else:  # SHED
        return ModeEffect(
            pressure_damping=0.6,
            decay_rate=0.2,
            reveal_speed=0.4,
            input_suppression=0.2,
        )
