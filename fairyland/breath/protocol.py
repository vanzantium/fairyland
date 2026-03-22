"""
Breath Protocol — the involuntary metronome.

No instructions. No "calm down." Just rhythm.

State    Icon  Timing   Output
CALM      ○    6-7s     Long, low haptic pulse
FLOW      ◐    4-5s     Gentle wave
EDGE      △    2-3s     Short double tap
OVERDRIVE (.)  —        3 seconds of silence
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from fairyland.engine.state import BreathState


@dataclass
class BreathPulse:
    """A single breath emission."""
    state: BreathState
    icon: str
    interval_seconds: float
    haptic_pattern: str
    timestamp: float


# Maps breath states to their physical expression
_BREATH_MAP = {
    BreathState.CALM: ("○", 6.5, "long_low"),
    BreathState.FLOW: ("◐", 4.5, "gentle_wave"),
    BreathState.EDGE: ("△", 2.5, "short_double_tap"),
    BreathState.OVERDRIVE: ("(.)", 3.0, "silence"),
}


class BreathProtocol:
    """
    Emits breath pulses based on the engine's current breath state.

    Haptics are capped. Audio is optional.
    Visual fallback if device can't vibrate.
    """

    def __init__(self):
        self._last_pulse_time: float = 0.0
        self._silence_start: Optional[float] = None

    def pulse(self, breath: BreathState) -> Optional[BreathPulse]:
        """
        Emit a pulse if enough time has elapsed since the last one.
        Returns None if it's not time yet.
        """
        now = time.time()
        icon, interval, haptic = _BREATH_MAP[breath]

        # overdrive — enforce 3 seconds of silence
        if breath == BreathState.OVERDRIVE:
            if self._silence_start is None:
                self._silence_start = now
            elapsed = now - self._silence_start
            if elapsed < 3.0:
                return None  # still in silence
            self._silence_start = None
            return BreathPulse(
                state=breath,
                icon=icon,
                interval_seconds=interval,
                haptic_pattern=haptic,
                timestamp=now,
            )

        self._silence_start = None

        # normal pulse — respect interval
        if now - self._last_pulse_time < interval:
            return None

        self._last_pulse_time = now
        return BreathPulse(
            state=breath,
            icon=icon,
            interval_seconds=interval,
            haptic_pattern=haptic,
            timestamp=now,
        )

    def force_pulse(self, breath: BreathState) -> BreathPulse:
        """Emit a pulse immediately, ignoring timing."""
        icon, interval, haptic = _BREATH_MAP[breath]
        now = time.time()
        self._last_pulse_time = now
        return BreathPulse(
            state=breath,
            icon=icon,
            interval_seconds=interval,
            haptic_pattern=haptic,
            timestamp=now,
        )
