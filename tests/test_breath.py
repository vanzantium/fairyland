"""Tests for the Breath Protocol."""

from fairyland.breath.protocol import BreathProtocol
from fairyland.engine.state import BreathState


class TestBreathProtocol:
    def test_force_pulse_calm(self):
        bp = BreathProtocol()
        p = bp.force_pulse(BreathState.CALM)
        assert p.icon == "○"
        assert p.haptic_pattern == "long_low"
        assert p.interval_seconds == 6.5

    def test_force_pulse_edge(self):
        bp = BreathProtocol()
        p = bp.force_pulse(BreathState.EDGE)
        assert p.icon == "△"
        assert p.haptic_pattern == "short_double_tap"

    def test_overdrive_silence(self):
        bp = BreathProtocol()
        # first overdrive pulse should return None (silence period)
        p = bp.pulse(BreathState.OVERDRIVE)
        assert p is None  # in 3-second silence
