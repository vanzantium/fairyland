"""Tests for rhythm sensing and the canvas rhythm pipeline."""

import pytest

from fairyland.app import create_app
from fairyland.engine.rhythm import extract_rhythm_signals
from fairyland.engine.spiral import SpiralEngine
from fairyland.engine.state import BreathState


def _calm_marks(n=3, start=0.0, gap_ms=4000):
    """Sparse, exploratory marks: slow cadence, spread positions."""
    return [
        {"t": start + i * gap_ms, "x": 0.1 + i * 0.3, "y": 0.2 + i * 0.25,
         "len": 0.2 + i * 0.1, "dur": 800}
        for i in range(n)
    ]


def _frantic_marks(n=14, start=0.0, gap_ms=180):
    """Rapid repetitive marks: same spot, same stroke, high cadence."""
    return [
        {"t": start + i * gap_ms, "x": 0.5, "y": 0.5, "len": 0.05, "dur": 90}
        for i in range(n)
    ]


class TestRhythmSignals:
    def test_empty_batch_is_stillness(self):
        s = extract_rhythm_signals([])
        assert s.rhythm == "flowing"
        assert s.emotional_direction == "settling"
        assert s.silence_ratio == 1.0
        assert s.repetition_score == 0.0
        assert s.tone is None

    def test_calm_marks_read_calm(self):
        s = extract_rhythm_signals(_calm_marks())
        assert s.rhythm == "flowing"
        assert s.repetition_score < 0.5

    def test_frantic_marks_read_staccato_and_repetitive(self):
        s = extract_rhythm_signals(_frantic_marks())
        assert s.rhythm == "staccato"
        assert s.repetition_score > 0.7

    def test_no_words_no_labels(self):
        s = extract_rhythm_signals(_frantic_marks())
        assert s.tone is None
        assert s.has_question is False
        assert s.has_exclamation is False

    def test_malformed_marks_skipped(self):
        s = extract_rhythm_signals([{"t": "bad"}, None and {}, {"x": 5}])
        # should not raise; bad fields clamp or skip
        assert s is not None


class TestRhythmStep:
    def test_frantic_input_raises_pressure(self):
        engine = SpiralEngine()
        for batch in range(6):
            signals = extract_rhythm_signals(_frantic_marks(start=batch * 2500))
            out = engine.rhythm_step(signals)
        assert engine.state.kernel.pressure > 0.4

    def test_overdrive_triggers_pip_silence(self):
        engine = SpiralEngine()
        # force the kernel to the brink, then push once more
        engine.state.kernel.pressure = 0.85
        engine.state.kernel.coherence = 0.2
        signals = extract_rhythm_signals(_frantic_marks())
        out = engine.rhythm_step(signals)
        assert out.pip_active is True
        assert out.text == ""  # silence carries no words

    def test_stillness_settles_pressure(self):
        engine = SpiralEngine()
        for batch in range(5):
            engine.rhythm_step(extract_rhythm_signals(_frantic_marks(start=batch * 2500)))
        high = engine.state.kernel.pressure
        for _ in range(8):
            engine.rhythm_step(extract_rhythm_signals([]))
        assert engine.state.kernel.pressure < high

    def test_output_carries_no_text(self):
        engine = SpiralEngine()
        out = engine.rhythm_step(extract_rhythm_signals(_calm_marks()))
        assert out.text == ""
        assert out.ritual_question is None
        assert out.weather is not None

    def test_anchor_appears_when_calm_and_rate_limited(self):
        engine = SpiralEngine()
        anchors = []
        for batch in range(20):
            # gentle presence: one calm mark per batch, then the engine
            # settles — anchors should surface, but only occasionally
            out = engine.rhythm_step(extract_rhythm_signals(
                [{"t": batch * 2500, "x": 0.3, "y": 0.4, "len": 0.2, "dur": 600}]
            ))
            if out.anchor:
                anchors.append((batch, out.anchor))
        assert len(anchors) >= 1          # calm presence does surface a verb
        assert len(anchors) <= 3          # but only occasionally
        for (_, word) in anchors:
            assert word in ["Make", "Sit", "Read", "Walk", "Find"]

    def test_abandoned_canvas_goes_quiet(self):
        """No marks at all -> no anchor, ever. The system does not perform
        to an empty room."""
        engine = SpiralEngine()
        for _ in range(30):
            out = engine.rhythm_step(extract_rhythm_signals([]))
            assert out.anchor is None


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestRhythmEndpoint:
    def _session(self, client):
        r = client.post("/session", json={"mode": "KID"})
        return r.get_json()["session_id"]

    def test_rhythm_roundtrip(self, client):
        sid = self._session(client)
        r = client.post("/rhythm", json={"session_id": sid, "marks": _calm_marks()})
        assert r.status_code == 200
        data = r.get_json()
        assert "breath" in data and "state" in data["breath"]
        assert "weather" in data
        assert "snapshot" in data

    def test_empty_heartbeat_ok(self, client):
        sid = self._session(client)
        r = client.post("/rhythm", json={"session_id": sid, "marks": []})
        assert r.status_code == 200

    def test_requires_session_id(self, client):
        r = client.post("/rhythm", json={"marks": []})
        assert r.status_code == 400

    def test_no_content_in_response(self, client):
        """The kids-mode response must never carry text or scores."""
        sid = self._session(client)
        r = client.post("/rhythm", json={"session_id": sid, "marks": _frantic_marks()})
        data = r.get_json()
        assert "text" not in data
        assert "signals" not in data
        assert "intervention" not in data

    def test_burn_after_canvas_session(self, client):
        sid = self._session(client)
        client.post("/rhythm", json={"session_id": sid, "marks": _calm_marks()})
        r = client.post("/burn", json={"session_id": sid})
        assert r.get_json()["burned"] is True

    def test_canvas_page_served(self, client):
        r = client.get("/canvas")
        assert r.status_code == 200
        assert b"paper" in r.data
