"""Integration tests for the Flask API."""

import json
import pytest

from fairyland.app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestHealthEndpoint:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.get_json()["status"] == "alive"


class TestSessionFlow:
    def test_create_session(self, client):
        r = client.post("/session", json={"mode": "KID"})
        assert r.status_code == 200
        data = r.get_json()
        assert "session_id" in data
        assert data["mode"] == "KID"

    def test_full_spiral_loop(self, client):
        # create session
        r = client.post("/session", json={"mode": "ADULT"})
        sid = r.get_json()["session_id"]

        # handshake
        r = client.post("/step", json={"session_id": sid, "text": "hello"})
        assert r.status_code == 200
        data = r.get_json()
        assert "text" in data
        assert data["breath"]["icon"] in ("○", "◐", "△", "(.)")

        # anchor
        r = client.post("/step", json={"session_id": sid, "text": "I'm in a forest"})
        data = r.get_json()
        assert data["snapshot"]["biome"] == "forest"

        # render
        r = client.post("/step", json={"session_id": sid, "text": "what is this fern?"})
        data = r.get_json()
        assert data["state"] in ("RITUAL", "RENDER", "HOLD")

        # ritual
        r = client.post("/step", json={"session_id": sid, "text": "interesting"})
        data = r.get_json()
        assert data.get("ritual_question") or data.get("text")

    def test_weather_endpoint(self, client):
        r = client.post("/session", json={})
        sid = r.get_json()["session_id"]
        client.post("/step", json={"session_id": sid, "text": "hi"})

        r = client.get(f"/weather?session_id={sid}")
        data = r.get_json()
        assert "weather" in data
        w = data["weather"]
        assert "rhythm" in w
        assert "tension" in w
        assert "flow" in w

    def test_burn_session(self, client):
        r = client.post("/session", json={})
        sid = r.get_json()["session_id"]
        client.post("/step", json={"session_id": sid, "text": "hi"})

        r = client.post("/burn", json={"session_id": sid})
        assert r.get_json()["burned"] is True

        # session gone
        r = client.get(f"/weather?session_id={sid}")
        assert r.status_code == 404


class TestBeaconEndpoint:
    def test_beacon_broadcast(self, client):
        r = client.post("/session", json={})
        sid = r.get_json()["session_id"]
        client.post("/step", json={"session_id": sid, "text": "hi"})

        r = client.get(f"/beacon?session_id={sid}")
        data = r.get_json()
        assert "skin_tightness" in data
        assert "scar_signature" in data


class TestHandshakeEndpoint:
    def test_handshake(self, client):
        r = client.post("/handshake", json={
            "local": {"skin_noise": 0.2, "scar_signature": 0.5, "reserve_surface": 0.6},
            "remote": {"skin_noise": 0.2, "scar_signature": 0.5, "reserve_surface": 0.6},
        })
        data = r.get_json()
        assert data["decision"] == "PRIORITY_HANDSHAKE"


class TestPlantData:
    def test_known_plant(self, client):
        r = client.get("/plant/bracken")
        assert r.status_code == 200
        data = r.get_json()
        assert data["species"] == "bracken"

    def test_unknown_plant(self, client):
        r = client.get("/plant/unicorn_flower")
        assert r.status_code == 404


class TestStepValidation:
    def test_missing_fields(self, client):
        r = client.post("/step", json={"session_id": "", "text": ""})
        assert r.status_code == 400
