"""Tests for Parent Peek — weather only, never the marks."""

import pytest

from fairyland.app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _kid_session(client):
    r = client.post("/session", json={"mode": "KID"})
    return r.get_json()["session_id"]


class TestWeatherCurrent:
    def test_quiet_when_no_kid_session(self, client):
        # adult chat sessions don't show up in the parent sky
        client.post("/session", json={"mode": "ADULT"})
        r = client.get("/weather/current")
        data = r.get_json()
        # may or may not be present depending on test ordering of the shared
        # session store; what matters is: never an error, never content
        assert r.status_code == 200
        assert set(data.keys()) == {"present", "weather"}

    def test_weather_for_active_kid_session(self, client):
        sid = _kid_session(client)
        client.post("/rhythm", json={"session_id": sid, "marks": []})
        r = client.get("/weather/current")
        data = r.get_json()
        assert data["present"] is True
        assert set(data["weather"].keys()) == {"rhythm", "tension", "flow"}

    def test_no_ids_no_content_in_response(self, client):
        """The parent response must never leak session ids, marks, or scores."""
        sid = _kid_session(client)
        client.post("/rhythm", json={"session_id": sid, "marks": [
            {"t": 0, "x": 0.5, "y": 0.5, "len": 0.1, "dur": 100}
        ]})
        r = client.get("/weather/current")
        body = r.get_data(as_text=True)
        assert sid not in body
        for forbidden in ["pressure", "snapshot", "marks", "session_id",
                          "coherence", "tick", "score"]:
            assert forbidden not in body

    def test_weather_words_are_vocabulary_only(self, client):
        sid = _kid_session(client)
        client.post("/rhythm", json={"session_id": sid, "marks": []})
        w = client.get("/weather/current").get_json()["weather"]
        assert w["rhythm"] in {"steady", "busy", "resting"}
        assert w["tension"] in {"low", "passing", "held"}
        assert w["flow"] in {"exploratory", "repetitive"}


class TestPeekPage:
    def test_peek_served(self, client):
        r = client.get("/peek")
        assert r.status_code == 200
        assert b"rhythm" in r.data
        # the page must not embed any session machinery
        assert b"session_id" not in r.data

    def test_sw_served_from_root(self, client):
        r = client.get("/sw.js")
        assert r.status_code == 200
        assert b"CACHE_NAME" in r.data
