"""
Fairyland — Flask API.

Minimal HTTP surface for the Spiral Engine.
No user tracking. No accounts. Ephemeral sessions by default.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from flask import Flask, jsonify, request

from fairyland.beacon.mesh import BeaconState, broadcast, handshake
from fairyland.breath.protocol import BreathProtocol
from fairyland.engine.shuffle import ProperShuffle, Track
from fairyland.engine.spiral import SpiralEngine
from fairyland.engine.state import RuntimeState, SessionMode
from fairyland.memory.engine import MemoryEngine

app = Flask(__name__)

# ---------------------------------------------------------------------------
# In-memory session store (ephemeral — no persistence by design)
# ---------------------------------------------------------------------------

_sessions: dict[str, dict] = {}

TATTOO_DIR = os.environ.get("FAIRYLAND_TATTOO_DIR", None)
DATA_DIR = Path(__file__).parent / "data"


def _get_or_create_session(sid: str) -> dict:
    if sid not in _sessions:
        memory = MemoryEngine(tattoo_dir=TATTOO_DIR)
        engine = SpiralEngine(pressure_baseline=memory.get_pressure_baseline())
        _sessions[sid] = {
            "engine": engine,
            "breath": BreathProtocol(),
            "memory": memory,
            "shuffle": None,  # created on demand
        }
    return _sessions[sid]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/health")
def health():
    return jsonify({"status": "alive"})


@app.route("/session", methods=["POST"])
def create_session():
    """Create a new ephemeral session. Returns session ID."""
    sid = uuid.uuid4().hex[:12]
    body = request.get_json(silent=True) or {}
    session = _get_or_create_session(sid)

    mode_str = body.get("mode", "ADULT").upper()
    try:
        mode = SessionMode(mode_str)
    except ValueError:
        mode = SessionMode.ADULT
    session["engine"].set_mode(mode)

    return jsonify({"session_id": sid, "mode": mode.value})


@app.route("/step", methods=["POST"])
def step():
    """
    Send user input through the Spiral Engine.

    Body: {"session_id": "...", "text": "..."}
    """
    body = request.get_json(force=True)
    sid = body.get("session_id", "")
    text = body.get("text", "")

    if not sid or not text:
        return jsonify({"error": "session_id and text required"}), 400

    session = _get_or_create_session(sid)
    engine: SpiralEngine = session["engine"]
    breath_proto: BreathProtocol = session["breath"]
    memory: MemoryEngine = session["memory"]

    # run spiral step
    output = engine.step(text)

    # breath pulse
    pulse = breath_proto.force_pulse(engine.state.breath)

    # friction logging with richer signals
    k = engine.state.kernel
    hesitation = "NONE"
    if engine.state.context.pip.active:
        hesitation = "STRONG"
    elif k.pressure > 0.5:
        hesitation = "MILD"

    signals = engine.last_signals
    memory.log(
        pressure=k.pressure,
        hesitation=hesitation,
        summary=text[:80],
        tick=engine.state.tick,
        tone=signals.tone if signals else None,
        rhythm=signals.rhythm if signals else None,
    )

    response = {
        "text": output.text,
        "state": output.state_name,
        "breath": {
            "state": pulse.state.value,
            "icon": pulse.icon,
            "haptic": pulse.haptic_pattern,
            "interval": pulse.interval_seconds,
        },
        "anchor": output.anchor,
        "pip_active": output.pip_active,
        "ritual_question": output.ritual_question,
        "weather": output.weather,
        "snapshot": engine.state.snapshot(),
    }

    # include new features when present
    if output.intervention:
        response["intervention"] = output.intervention
    if output.drift_nudge:
        response["drift_nudge"] = output.drift_nudge
    if output.oscillator_mode:
        response["oscillator_mode"] = output.oscillator_mode
    if output.signals:
        response["signals"] = output.signals

    return jsonify(response)


@app.route("/weather", methods=["GET"])
def weather():
    """Parent mode: weather only, no content."""
    sid = request.args.get("session_id", "")
    if sid not in _sessions:
        return jsonify({"error": "unknown session"}), 404
    engine: SpiralEngine = _sessions[sid]["engine"]
    return jsonify({"weather": engine.get_weather()})


@app.route("/drift", methods=["GET"])
def drift():
    """Bias drift HUD — tracks parasocial risk, echo, narrowing."""
    sid = request.args.get("session_id", "")
    if sid not in _sessions:
        return jsonify({"error": "unknown session"}), 404
    engine: SpiralEngine = _sessions[sid]["engine"]
    return jsonify({"drift": engine.get_drift_hud()})


@app.route("/burn", methods=["POST"])
def burn():
    """Burn session memory. Only tattoos survive."""
    body = request.get_json(force=True)
    sid = body.get("session_id", "")
    if sid not in _sessions:
        return jsonify({"error": "unknown session"}), 404
    session = _sessions[sid]
    session["memory"].burn_session()
    del _sessions[sid]
    return jsonify({"burned": True})


@app.route("/dwell", methods=["POST"])
def dwell():
    """Trigger nightly dwell cycle for a session."""
    body = request.get_json(force=True)
    sid = body.get("session_id", "")
    if sid not in _sessions:
        return jsonify({"error": "unknown session"}), 404
    memory: MemoryEngine = _sessions[sid]["memory"]
    tattoo = memory.dwell()
    return jsonify({
        "tattoo": tattoo,
        "scar_signature": memory.state.scar_signature,
        "total_tattoos": len(memory.state.code_tattoos),
        "patterns": memory.state.patterns,
    })


@app.route("/beacon", methods=["GET"])
def beacon_route():
    """Get the beacon broadcast for a session."""
    sid = request.args.get("session_id", "")
    if sid not in _sessions:
        return jsonify({"error": "unknown session"}), 404
    engine: SpiralEngine = _sessions[sid]["engine"]
    memory: MemoryEngine = _sessions[sid]["memory"]
    b = broadcast(engine.state.kernel, scar=memory.state.scar_signature)
    return jsonify({
        "skin_tightness": round(b.skin_tightness, 3),
        "skin_noise": round(b.skin_noise, 3),
        "reserve_surface": round(b.reserve_surface, 3),
        "pull_signal": round(b.pull_signal, 3),
        "pursuit_drive": round(b.pursuit_drive, 3),
        "cooldown": round(b.cooldown, 3),
        "scar_signature": round(b.scar_signature, 3),
    })


@app.route("/handshake", methods=["POST"])
def handshake_route():
    """Test handshake compatibility between two beacon states."""
    body = request.get_json(force=True)
    local = BeaconState(**body.get("local", {}))
    remote = BeaconState(**body.get("remote", {}))
    decision = handshake(local, remote)
    return jsonify({"decision": decision.name})


@app.route("/shuffle/start", methods=["POST"])
def shuffle_start():
    """Start a Proper Shuffle session with a playlist."""
    body = request.get_json(force=True)
    sid = body.get("session_id", "")
    tracks_data = body.get("tracks", [])

    if sid not in _sessions:
        return jsonify({"error": "unknown session"}), 404

    tracks = [Track(
        id=t.get("id", str(i)),
        title=t.get("title", f"Track {i}"),
        duration_s=t.get("duration_s", 180.0),
        mood=t.get("mood", "neutral"),
    ) for i, t in enumerate(tracks_data)]

    shuffle = ProperShuffle(tracks)
    _sessions[sid]["shuffle"] = shuffle
    return jsonify({"started": True, "track_count": len(tracks)})


@app.route("/shuffle/next", methods=["POST"])
def shuffle_next():
    """Get the next track/silence/exit from the shuffle."""
    body = request.get_json(force=True)
    sid = body.get("session_id", "")

    if sid not in _sessions:
        return jsonify({"error": "unknown session"}), 404

    shuffle: ProperShuffle = _sessions[sid].get("shuffle")
    if not shuffle:
        return jsonify({"error": "no shuffle session"}), 400

    out = shuffle.next()
    result = {
        "silence": out.silence,
        "anchor_cue": out.anchor_cue,
        "exit_cue": out.exit_cue,
    }
    if out.track:
        result["track"] = {
            "id": out.track.id,
            "title": out.track.title,
            "duration_s": out.track.duration_s,
            "mood": out.track.mood,
        }
    return jsonify(result)


@app.route("/plant/<species>")
def plant_data(species: str):
    """Serve plant card data."""
    plant_file = DATA_DIR / "plants" / f"{species}.plant.json"
    if not plant_file.exists():
        return jsonify({"error": "unknown species"}), 404
    data = json.loads(plant_file.read_text())
    return jsonify(data)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def create_app():
    return app


if __name__ == "__main__":
    app.run(debug=True, port=5000)
