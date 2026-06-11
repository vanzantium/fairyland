"""Tests for the listening layer — feel during playback, settle after.

The calibration doctrine (Music Mode update doc): if a groovy song and a
chaotic song leave the same residue, the feeling layer is noise. These
tests pin that the residues differ in predictable directions.
"""

import pytest

from fairyland.app import create_app
from fairyland.engine.listening import ListeningBuffer, settle
from fairyland.engine.state import KernelState


def _groovy_packets(seconds=20, rate_hz=15):
    """Steady warm music: regular onsets every 500ms, bass-heavy, mid amp."""
    packets = []
    n = int(seconds * rate_hz)
    for i in range(n):
        t = i * (1000 / rate_hz)
        onset = (i % round(0.5 * rate_hz)) == 0  # every 500ms — locked groove
        packets.append({"t": t, "low": 0.7, "mid": 0.4, "high": 0.2,
                        "amp": 0.5, "onset": onset})
    return packets


def _chaotic_packets(seconds=20, rate_hz=15):
    """Erratic harsh music: irregular onsets, treble-heavy, loud."""
    packets = []
    n = int(seconds * rate_hz)
    gaps = [0.13, 0.91, 0.27, 1.9, 0.08, 0.55, 2.6, 0.19, 1.2, 0.07]
    next_onset = 0.0
    gi = 0
    for i in range(n):
        t_s = i / rate_hz
        onset = False
        if t_s >= next_onset:
            onset = True
            next_onset += gaps[gi % len(gaps)]
            gi += 1
        packets.append({"t": t_s * 1000, "low": 0.15, "mid": 0.35, "high": 0.8,
                        "amp": 0.85, "onset": onset})
    return packets


class TestResidue:
    def test_empty_buffer_is_neutral(self):
        buf = ListeningBuffer()
        r = buf.residue()
        assert r["impressions"] == 0
        assert r["swing_ratio"] == 0.5

    def test_groovy_and_chaotic_read_differently(self):
        """The calibration test: love and hate must not look the same."""
        groovy = ListeningBuffer()
        groovy.feel(_groovy_packets())
        chaotic = ListeningBuffer()
        chaotic.feel(_chaotic_packets())

        rg, rc = groovy.residue(), chaotic.residue()
        assert rg["swing_ratio"] > rc["swing_ratio"]
        assert rg["warmth"] > rc["warmth"]
        assert rc["tension"] > rg["tension"]

    def test_groovy_reads_groovy(self):
        buf = ListeningBuffer()
        buf.feel(_groovy_packets())
        r = buf.residue()
        assert r["swing_ratio"] > 0.6
        assert r["warmth"] > 0.4

    def test_malformed_packets_skipped(self):
        buf = ListeningBuffer()
        landed = buf.feel([{"t": "bad"}, None, {"low": 99}, 42])
        assert landed >= 0  # never raises

    def test_buffer_bounded(self):
        buf = ListeningBuffer()
        buf.feel([{"t": i, "amp": 0.5} for i in range(6000)])
        assert len(buf.impressions) <= ListeningBuffer.MAX_IMPRESSIONS


class TestSettle:
    def test_groovy_music_lifts_groove_and_warmth(self):
        buf = ListeningBuffer()
        buf.feel(_groovy_packets())
        k = KernelState()
        k.groove = 0.4
        k.temperature = 0.2
        report = settle(k, buf.residue())
        assert report["settled"] is True
        assert k.groove > 0.4          # the rhythm felt good
        assert k.temperature > 0.2     # bass warmth lingers

    def test_chaotic_music_raises_pressure(self):
        buf = ListeningBuffer()
        buf.feel(_chaotic_packets())
        k = KernelState()
        before = k.pressure
        settle(k, buf.residue())
        assert k.pressure > before

    def test_empty_residue_changes_nothing(self):
        buf = ListeningBuffer()
        k = KernelState()
        snapshot = (k.groove, k.pressure, k.temperature, k.coherence)
        settle(k, buf.residue())
        assert (k.groove, k.pressure, k.temperature, k.coherence) == snapshot


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestListenEndpoints:
    def _session(self, client):
        return client.post("/session", json={"mode": "KID"}).get_json()["session_id"]

    def test_listen_accumulates_without_touching_kernel(self, client):
        sid = self._session(client)
        before = client.get("/weather/current").get_json()
        r = client.post("/listen", json={"session_id": sid,
                                         "packets": _groovy_packets(seconds=5)})
        assert r.status_code == 200
        assert r.get_json()["felt"] > 0
        # feeling is not processing: weather unchanged until settle
        after = client.get("/weather/current").get_json()
        assert before == after

    def test_settle_shifts_kernel_once(self, client):
        sid = self._session(client)
        client.post("/listen", json={"session_id": sid, "packets": _groovy_packets()})
        r = client.post("/listen/settle", json={"session_id": sid})
        data = r.get_json()
        assert data["settled"] is True
        assert data["residue"]["impressions"] > 0
        assert "weather" in data
        # the buffer cleared: settling again is a no-op
        r2 = client.post("/listen/settle", json={"session_id": sid}).get_json()
        assert r2["residue"]["impressions"] == 0

    def test_requires_session(self, client):
        assert client.post("/listen", json={"packets": []}).status_code == 400
        assert client.post("/listen/settle", json={"session_id": "ghost"}).status_code == 404
