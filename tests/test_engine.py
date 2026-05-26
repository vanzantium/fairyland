"""Tests for the Spiral Engine core loop."""

import pytest

from fairyland.engine.spiral import SpiralEngine, SpiralOutput
from fairyland.engine.state import (
    BreathState,
    RuntimeState,
    SessionMode,
    SpiralState,
)


class TestSpiralEngineHandshake:
    def test_starts_in_handshake(self):
        engine = SpiralEngine()
        assert engine.state.spiral == SpiralState.HANDSHAKE

    def test_handshake_detects_kid_mode(self):
        engine = SpiralEngine()
        out = engine.step("I'm a kid")
        assert engine.state.context.T.mode == SessionMode.KID
        assert engine.state.spiral == SpiralState.ANCHOR

    def test_handshake_detects_coder_mode(self):
        engine = SpiralEngine()
        out = engine.step("developer here")
        assert engine.state.context.T.mode == SessionMode.CODER

    def test_handshake_defaults_to_adult(self):
        engine = SpiralEngine()
        out = engine.step("hello")
        assert engine.state.context.T.mode == SessionMode.ADULT


class TestSpiralEngineAnchoring:
    def _make_anchored_engine(self, handshake_text="hello", anchor_text="I'm in the forest"):
        engine = SpiralEngine()
        engine.step(handshake_text)
        out = engine.step(anchor_text)
        return engine, out

    def test_anchor_detects_biome(self):
        engine, out = self._make_anchored_engine()
        assert engine.state.context.T.biome == "forest"
        assert engine.state.spiral == SpiralState.RENDER

    def test_anchor_unknown_enters_hold(self):
        engine = SpiralEngine()
        engine.step("hello")
        out = engine.step("something weird")
        assert engine.state.spiral == SpiralState.HOLD
        assert out.pip_active

    def test_hold_then_render(self):
        engine = SpiralEngine()
        engine.step("hello")
        engine.step("something weird")  # -> HOLD
        out = engine.step("trees everywhere")  # -> RENDER
        assert engine.state.spiral == SpiralState.RENDER


class TestSpiralEngineRenderRitual:
    def test_render_kid_mode_never_ids_plant(self):
        engine = SpiralEngine()
        engine.step("kid here")
        engine.step("I'm in the meadow")
        out = engine.step("this plant stings")
        # kid mode should never name the plant
        assert "nettle" not in out.text.lower()
        assert "urtica" not in out.text.lower()

    def test_ritual_returns_noticing_question(self):
        engine = SpiralEngine()
        engine.step("hello")
        engine.step("forest walk")
        engine.step("what's this?")  # RENDER
        out = engine.step("interesting")  # RITUAL
        assert out.ritual_question is not None

    def test_ritual_loops_back_to_render(self):
        engine = SpiralEngine()
        engine.step("hello")
        engine.step("forest walk")
        engine.step("look at this")
        engine.step("cool")  # RITUAL
        assert engine.state.spiral == SpiralState.RENDER


class TestBreathAndPip:
    def test_calm_at_low_pressure(self):
        engine = SpiralEngine()
        engine.step("hi")
        assert engine.state.breath in (BreathState.CALM, BreathState.FLOW)

    def test_overdrive_triggers_pip(self):
        engine = SpiralEngine()
        engine.step("hello")
        engine.step("forest")
        # force high pressure
        engine.state.kernel.pressure = 0.9
        out = engine.step("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" * 5)
        assert engine.state.breath == BreathState.OVERDRIVE
        assert out.pip_active
        assert "(.) " in out.text or "…" in out.text


class TestWeather:
    def test_weather_returns_three_fields(self):
        engine = SpiralEngine()
        w = engine.get_weather()
        assert "rhythm" in w
        assert "tension" in w
        assert "flow" in w

    def test_weather_no_content(self):
        engine = SpiralEngine()
        engine.step("hi")
        engine.step("forest")
        engine.step("what is this plant?")
        w = engine.get_weather()
        # weather should never contain plant names or user input
        for v in w.values():
            assert v in ("steady", "busy", "resting", "low", "passing", "held", "exploratory", "repetitive")


class TestHistory:
    def test_history_bounded(self):
        engine = SpiralEngine()
        for i in range(20):
            engine.step(f"message {i}")
        assert len(engine.state.history) <= 12
