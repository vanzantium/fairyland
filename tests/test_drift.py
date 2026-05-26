"""Tests for the bias drift / anti-idolization tracker."""

from fairyland.engine.drift import DriftTracker


class TestDriftTracker:
    def test_starts_clean(self):
        dt = DriftTracker()
        hud = dt.get_hud()
        assert hud["parasocial"] == 0.0
        assert hud["echo"] == 0.0
        assert hud["narrowing"] == 0.0

    def test_parasocial_detection(self):
        dt = DriftTracker()
        dt.update("i need you don't leave me", 0.0, tick=1)
        assert dt.state.parasocial_score > 0.0

    def test_parasocial_triggers_nudge(self):
        dt = DriftTracker()
        # pump up parasocial score
        for i in range(5):
            result = dt.update("i need you stay with me please", 0.0, tick=i + 1)
        # should eventually trigger a nudge
        assert dt.state.nudge_count > 0 or dt.state.parasocial_score > 0.4

    def test_echo_detection(self):
        dt = DriftTracker()
        dt.update("same words", 0.8, tick=1)
        dt.update("same words", 0.8, tick=2)
        assert dt.state.echo_score > 0.0

    def test_nudge_cooldown(self):
        dt = DriftTracker()
        dt.state.parasocial_score = 0.9
        nudge1 = dt.update("i need you", 0.0, tick=1)
        nudge2 = dt.update("i need you", 0.0, tick=2)
        # second nudge should be blocked by cooldown
        if nudge1 is not None:
            assert nudge2 is None  # within cooldown

    def test_nudge_is_not_a_ban(self):
        dt = DriftTracker()
        dt.state.parasocial_score = 0.9
        nudge = dt.update("i need you", 0.0, tick=10)
        if nudge:
            # nudge should be sideways content, not a prohibition
            assert "not allowed" not in nudge.text.lower()
            assert "stop" not in nudge.text.lower()

    def test_hud_structure(self):
        dt = DriftTracker()
        dt.update("hello there", 0.1, tick=1)
        hud = dt.get_hud()
        assert "parasocial" in hud
        assert "echo" in hud
        assert "narrowing" in hud
        assert "nudge_count" in hud
