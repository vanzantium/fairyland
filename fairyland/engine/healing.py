"""
Micro-Healing Interventions — non-therapeutic regulation nudges.

Each intervention is a playful, aesthetic artifact presented
as part of the environment. Never a prescription.

Selection is based on current kernel state — the system
picks what fits the regulatory moment, not what's "needed."
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .state import KernelState, Mode


@dataclass
class Intervention:
    """A micro-healing nudge."""
    name: str
    verb: str       # one-word action
    artifact: str   # what appears (aesthetic, not instructional)
    domain: str     # what kernel dimension it addresses


# The five interventions from the spec
SWEETGRASS_TRAIL = Intervention(
    name="Sweetgrass Trail",
    verb="wander",
    artifact="A faint trail of sweetgrass scent drifts left.",
    domain="redirection",
)

SALT_OF_FOCUS = Intervention(
    name="Salt of Focus",
    verb="taste",
    artifact="A grain of salt on the tongue. The world sharpens.",
    domain="concentration",
)

RAT_ROOT_DECOCTION = Intervention(
    name="Rat Root Decoction",
    verb="breathe",
    artifact="Something loosens in the chest. A knot unties itself.",
    domain="tension_release",
)

NIGREDO_DUST = Intervention(
    name="Nigredo Dust",
    verb="release",
    artifact="Dark powder settles. What was held dissolves.",
    domain="letting_go",
)

GRANDFATHERS_WHISPER = Intervention(
    name="Grandfather's Whisper",
    verb="listen",
    artifact="A low voice, far away. Something about the ground beneath you.",
    domain="grounding",
)

_ALL_INTERVENTIONS = [
    SWEETGRASS_TRAIL,
    SALT_OF_FOCUS,
    RAT_ROOT_DECOCTION,
    NIGREDO_DUST,
    GRANDFATHERS_WHISPER,
]


def select_intervention(kernel: KernelState, mode: Mode) -> Optional[Intervention]:
    """
    Select the most appropriate micro-healing intervention
    based on current kernel state.

    Returns None if no intervention is warranted (system is calm).
    """
    # no intervention if pressure is low and coherence is high
    if kernel.pressure < 0.3 and kernel.coherence > 0.7:
        return None

    # high stress, low reserve -> grounding
    if kernel.stress > 0.6 or kernel.reserve < 0.3:
        return GRANDFATHERS_WHISPER

    # high pressure, temperature rising -> tension release
    if kernel.pressure > 0.6 and kernel.temperature > 0.6:
        return RAT_ROOT_DECOCTION

    # loss or debt accumulating -> permission to let go
    if kernel.loss > 0.4 or kernel.debt > 0.5:
        return NIGREDO_DUST

    # low coherence, scattered -> focus
    if kernel.coherence < 0.5 and kernel.temperature > 0.4:
        return SALT_OF_FOCUS

    # moderate pressure, needs gentle redirect
    if kernel.pressure > 0.4:
        return SWEETGRASS_TRAIL

    # DWELL mode always gets a gentle nudge
    if mode == Mode.DWELL:
        return SWEETGRASS_TRAIL

    return None
