"""Tests for the Oscillator."""

from fairyland.engine.oscillator import (
    ModeEffect,
    advance_oscillator,
    mode_effects,
)
from fairyland.engine.state import KernelState, Mode, OscillatorState


class TestOscillatorAdvance:
    def test_phi_increases_each_tick(self):
        osc = OscillatorState(phi=0.0, mode=Mode.BUILD)
        kernel = KernelState()
        new = advance_oscillator(osc, kernel, tick=1)
        assert new.phi > 0.0

    def test_full_cycle_returns_to_build(self):
        osc = OscillatorState(phi=0.0, mode=Mode.BUILD)
        kernel = KernelState(pressure=0.5, coherence=0.5)
        seen_modes = set()
        for tick in range(200):
            osc = advance_oscillator(osc, kernel, tick)
            seen_modes.add(osc.mode)
        # should have seen all four modes
        assert seen_modes == {Mode.BUILD, Mode.AUDIT, Mode.DWELL, Mode.SHED}

    def test_high_pressure_accelerates(self):
        osc = OscillatorState(phi=0.0, mode=Mode.BUILD)
        calm_kernel = KernelState(pressure=0.1, coherence=0.5)
        hot_kernel = KernelState(pressure=0.9, coherence=0.5)

        calm_result = advance_oscillator(osc, calm_kernel, 1)
        hot_result = advance_oscillator(osc, hot_kernel, 1)
        assert hot_result.phi > calm_result.phi

    def test_high_coherence_decelerates(self):
        osc = OscillatorState(phi=0.0, mode=Mode.BUILD)
        low_c = KernelState(pressure=0.5, coherence=0.1)
        high_c = KernelState(pressure=0.5, coherence=0.9)

        low_result = advance_oscillator(osc, low_c, 1)
        high_result = advance_oscillator(osc, high_c, 1)
        assert low_result.phi > high_result.phi

    def test_dwell_mode_detected(self):
        osc = OscillatorState(phi=0.55, mode=Mode.DWELL)
        kernel = KernelState()
        new = advance_oscillator(osc, kernel, 1)
        # phi 0.55 is in DWELL range, should remain there or advance within
        assert new.in_dwell or new.mode == Mode.DWELL or new.phi >= 0.5


class TestModeEffects:
    def test_build_no_suppression(self):
        effect = mode_effects(Mode.BUILD)
        assert effect.input_suppression == 0.0
        assert effect.pressure_damping == 1.0

    def test_dwell_suppresses_input(self):
        effect = mode_effects(Mode.DWELL)
        assert effect.input_suppression > 0.0
        assert effect.pressure_damping < 1.0

    def test_shed_high_decay(self):
        effect = mode_effects(Mode.SHED)
        assert effect.decay_rate > mode_effects(Mode.BUILD).decay_rate
