"""
Beacon & Handshake — regulatory mesh between instances.

Beacon broadcasts the current regulatory surface (scars, tightness, noise, reserve).
Handshake logic decides whether two instances should interact.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from fairyland.engine.state import KernelState


class HandshakeDecision(Enum):
    IGNORE = auto()
    STANDARD_HANDSHAKE = auto()
    PRIORITY_HANDSHAKE = auto()


@dataclass
class BeaconState:
    """What an instance broadcasts to the mesh."""
    skin_tightness: float = 0.0
    skin_noise: float = 0.0
    reserve_surface: float = 1.0
    pull_signal: float = 0.0
    pursuit_drive: float = 0.0
    cooldown: float = 0.0
    scar_signature: float = 0.0


def broadcast(kernel: KernelState, scar: float = 0.0) -> BeaconState:
    """Derive a beacon broadcast from current kernel state."""
    return BeaconState(
        skin_tightness=kernel.stress,
        skin_noise=1.0 - kernel.coherence,
        reserve_surface=kernel.reserve,
        pull_signal=max(0.0, kernel.pressure - 0.5),
        pursuit_drive=kernel.temperature,
        cooldown=kernel.debt,
        scar_signature=scar,
    )


def handshake(local: BeaconState, remote: BeaconState) -> HandshakeDecision:
    """
    Decide how two beacons should interact.

    1. Noise shield — if both high noise -> IGNORE
    2. Compatibility delta < 0.2 and reserves match -> PRIORITY_HANDSHAKE
    3. Mismatch > 0.8 -> IGNORE
    4. Default -> STANDARD_HANDSHAKE
    """
    # 1. noise shield
    if local.skin_noise > 0.7 and remote.skin_noise > 0.7:
        return HandshakeDecision.IGNORE

    # 2. compatibility delta
    delta = abs(local.scar_signature - remote.scar_signature)
    reserve_match = abs(local.reserve_surface - remote.reserve_surface) < 0.3

    if delta < 0.2 and reserve_match:
        return HandshakeDecision.PRIORITY_HANDSHAKE

    # 3. mismatch
    if delta > 0.8:
        return HandshakeDecision.IGNORE

    # 4. default
    return HandshakeDecision.STANDARD_HANDSHAKE
