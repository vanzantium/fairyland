"""Tests for bridge API endpoints."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from fairyland.app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def session_id(client):
    resp = client.post("/session", json={})
    return resp.get_json()["session_id"]


def test_bridge_status_no_pip(client):
    resp = client.get("/bridge/status")
    data = resp.get_json()
    assert resp.status_code == 200
    assert "pip_connected" in data
    assert "active_sessions" in data


def test_bridge_thermal_no_pip(client):
    resp = client.get("/bridge/thermal")
    assert resp.status_code in (400, 404)


def test_bridge_governor_no_pip(client):
    resp = client.get("/bridge/governor")
    assert resp.status_code in (400, 404)


def test_bridge_friction(client, session_id):
    client.post("/step", json={"session_id": session_id, "text": "hello"})
    resp = client.get(f"/bridge/friction?session_id={session_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["session_id"] == session_id
    assert data["tick_count"] >= 1
    assert "avg_pressure" in data
    assert "pip_events" in data
    assert len(data["pip_events"]) > 0


def test_bridge_friction_unknown_session(client):
    resp = client.get("/bridge/friction?session_id=nonexistent")
    assert resp.status_code == 404


def test_bridge_thermal_with_pip_dir(client, tmp_path):
    import fairyland.app as app_module
    old_dir = app_module.PIP_DATA_DIR
    app_module.PIP_DATA_DIR = str(tmp_path)

    dream = {
        "thermal_state": {
            "coherence": 0.7,
            "pressure": 0.3,
            "drift": 0.1,
            "groove": 0.6,
            "integration_debt": 0.2,
            "scar": 0.4,
        }
    }
    (tmp_path / "s25_latest_dream.json").write_text(json.dumps(dream))

    try:
        resp = client.get("/bridge/thermal")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["coherence"] == 0.7
        assert data["groove"] == 0.6
    finally:
        app_module.PIP_DATA_DIR = old_dir


def test_bridge_governor_with_state(client, tmp_path):
    import fairyland.app as app_module
    old_dir = app_module.PIP_DATA_DIR
    app_module.PIP_DATA_DIR = str(tmp_path)

    state = {
        "daily_budget_tokens": 60000,
        "daily_used_tokens": 10000,
    }
    (tmp_path / "token_governor_state.json").write_text(json.dumps(state))

    try:
        resp = client.get("/bridge/governor")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["mode"] == "BUILD"
        assert data["reveal_speed"] == 0.7
        assert data["daily_budget"] == 60000
    finally:
        app_module.PIP_DATA_DIR = old_dir


def test_bridge_status_with_pip_dir(client, tmp_path):
    import fairyland.app as app_module
    old_dir = app_module.PIP_DATA_DIR
    app_module.PIP_DATA_DIR = str(tmp_path)

    dream = {"thermal_state": {"coherence": 0.5}}
    (tmp_path / "s25_latest_dream.json").write_text(json.dumps(dream))

    try:
        resp = client.get("/bridge/status")
        data = resp.get_json()
        assert data["pip_connected"] is True
        assert data["thermal_available"] is True
    finally:
        app_module.PIP_DATA_DIR = old_dir
