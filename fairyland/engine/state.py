"""
Core state objects for the Fairyland engine.

These are the registers, kernel, and oscillator states that
drive the Spiral Engine's regulatory loop.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Mode(Enum):
    """Oscillator modes — the engine's macro rhythm."""
    BUILD = auto()
    AUDIT = auto()
    DWELL = auto()
    SHED = auto()


class SessionMode(Enum):
    """Who is using the system right now."""
    KID = "KID"
    ADULT = "ADULT"
    CODER = "CODER"


class SpiralState(Enum):
    """State machine positions for the Spiral Engine."""
    HANDSHAKE = "HANDSHAKE"
    ANCHOR = "ANCHOR"
    HOLD = "HOLD"
    RENDER = "RENDER"
    RITUAL = "RITUAL"


class BreathState(Enum):
    """Breath protocol states — the involuntary metronome."""
    CALM = "CALM"       # 6-7s, long low pulse
    FLOW = "FLOW"       # 4-5s, gentle wave
    EDGE = "EDGE"       # 2-3s, short double tap
    OVERDRIVE = "OVERDRIVE"  # silence


# ---------------------------------------------------------------------------
# Kernel & Regulatory State
# ---------------------------------------------------------------------------

@dataclass
class KernelState:
    """The engine's internal regulatory state."""
    reserve: float = 1.0
    recovery: float = 0.5
    stress: float = 0.0
    loss: float = 0.0
    debt: float = 0.0
    temperature: float = 0.5
    pressure: float = 0.0
    groove: float = 0.5
    coherence: float = 1.0
    semantic_meaning: float = 0.5


@dataclass
class SelfModelState:
    """The system's self-awareness register."""
    dominant_patterns: List[str] = field(default_factory=list)
    compression_confidence: float = 0.5
    loop_awareness: float = 0.0
    self_prediction_error: float = 0.0


@dataclass
class OscillatorState:
    """Phase oscillator — controls the engine's macro rhythm."""
    phi: float = 0.0
    mode: Mode = Mode.BUILD
    phase: str = "rising"
    in_dwell: bool = False


# ---------------------------------------------------------------------------
# Three-register context  (t), (.), (T)
# ---------------------------------------------------------------------------

@dataclass
class MicroContext:
    """(t) — Micro Rhythm. Immediate user state."""
    last_input: Optional[str] = None
    last_choice: Optional[str] = None
    mood: Optional[str] = None
    tone: Optional[str] = None
    emotion: Optional[str] = None


@dataclass
class PipContext:
    """(.) — Pip / Pause. The sanctioned hold state."""
    hold_reason: Optional[str] = None
    question: Optional[str] = None
    active: bool = False


@dataclass
class MacroContext:
    """(T) — Macro Arc. Structural session context."""
    mode: SessionMode = SessionMode.ADULT
    biome: Optional[str] = None
    intent: Optional[str] = None
    tone: str = "crushed_black"
    safety_flags: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Unified session context
# ---------------------------------------------------------------------------

@dataclass
class SessionContext:
    """Three-register context: (t), (.), (T)."""
    t: MicroContext = field(default_factory=MicroContext)
    pip: PipContext = field(default_factory=PipContext)
    T: MacroContext = field(default_factory=MacroContext)


# ---------------------------------------------------------------------------
# History ring buffer
# ---------------------------------------------------------------------------

def make_history(maxlen: int = 12) -> deque:
    """Create a bounded ring buffer for session history."""
    return deque(maxlen=maxlen)


# ---------------------------------------------------------------------------
# Full runtime state
# ---------------------------------------------------------------------------

@dataclass
class RuntimeState:
    """Complete runtime state for one engine instance."""
    kernel: KernelState = field(default_factory=KernelState)
    self_model: SelfModelState = field(default_factory=SelfModelState)
    oscillator: OscillatorState = field(default_factory=OscillatorState)
    context: SessionContext = field(default_factory=SessionContext)
    spiral: SpiralState = SpiralState.HANDSHAKE
    breath: BreathState = BreathState.CALM
    history: deque = field(default_factory=lambda: make_history())
    session_start: float = field(default_factory=time.time)
    tick: int = 0

    def snapshot(self) -> dict:
        """Return a minimal snapshot for external consumers."""
        return {
            "spiral": self.spiral.value,
            "breath": self.breath.value,
            "mode": self.context.T.mode.value,
            "biome": self.context.T.biome,
            "coherence": round(self.kernel.coherence, 2),
            "pressure": round(self.kernel.pressure, 2),
            "tick": self.tick,
            "pip_active": self.context.pip.active,
        }
