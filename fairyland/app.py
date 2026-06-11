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

from flask import Flask, jsonify, request, render_template, send_from_directory

from fairyland.beacon.mesh import BeaconState, broadcast, handshake
from fairyland.breath.protocol import BreathProtocol
from fairyland.bridge import (
    GovernorState,
    PipThermal,
    extract_session_friction,
    friction_to_pip_events,
    governor_to_reveal_speed,
    load_governor_state,
    load_pip_thermal,
    load_tiered_memory,
    save_tiered_memory,
    seed_kernel_from_pip,
)
from fairyland.engine.rhythm import extract_rhythm_signals
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
PIP_DATA_DIR = os.environ.get("FAIRYLAND_PIP_DIR", None)
DATA_DIR = Path(__file__).parent / "data"

# the user's own music, dropped into a local folder. nothing is fetched,
# nothing is recommended — the library is whatever the household put there.
AUDIO_EXTENSIONS = {".mp3", ".ogg", ".m4a", ".wav", ".flac", ".webm", ".opus", ".aac"}


def _music_dir() -> Path:
    return Path(os.environ.get("FAIRYLAND_MUSIC_DIR")
                or Path(__file__).parent / "music")


def _scan_music() -> list[Path]:
    base = _music_dir()
    if not base.is_dir():
        return []
    return sorted(
        p for p in base.iterdir()
        if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
    )


def _get_or_create_session(sid: str, pip_seed: bool = True) -> dict:
    if sid not in _sessions:
        memory = MemoryEngine(tattoo_dir=TATTOO_DIR)
        engine = SpiralEngine(pressure_baseline=memory.get_pressure_baseline())
        _sessions[sid] = {
            "engine": engine,
            "breath": BreathProtocol(),
            "memory": memory,
            "shuffle": None,
        }
        if pip_seed and PIP_DATA_DIR:
            _seed_from_pip(engine, PIP_DATA_DIR)
    return _sessions[sid]


def _seed_from_pip(engine: SpiralEngine, pip_dir: str) -> None:
    """Seed a new session's kernel from PipV0's latest thermal state."""
    p = Path(pip_dir)
    thermal_path = p / "s25_latest_dream.json"
    thermal = load_pip_thermal(str(thermal_path))
    if not thermal:
        return
    tiered_path = p / "tiered_memory.json"
    tiered = load_tiered_memory(str(tiered_path))
    seed_kernel_from_pip(engine.state.kernel, thermal, tiered)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/canvas")
def canvas():
    """Kids mode — the blank canvas instrument. No words, no scores."""
    return render_template("canvas.html")


@app.route("/sw.js")
def service_worker():
    """Serve the service worker from the root so its scope covers all pages
    (a worker registered from /static/ could only control /static/)."""
    return app.send_static_file("sw.js")


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


@app.route("/rhythm", methods=["POST"])
def rhythm():
    """
    Canvas telemetry step — the kids-mode counterpart of /step.

    Body: {"session_id": "...", "marks": [{"t": ms, "x": 0..1, "y": 0..1,
            "len": 0..2, "dur": ms}, ...]}

    An empty marks list is a valid heartbeat: stillness lets pressure settle.
    No content is read or stored — only rhythm. The friction log gets a
    pressure number with an empty summary, and the whole session burns on exit.
    """
    body = request.get_json(force=True)
    sid = body.get("session_id", "")
    if not sid:
        return jsonify({"error": "session_id required"}), 400

    session = _get_or_create_session(sid)
    engine: SpiralEngine = session["engine"]
    breath_proto: BreathProtocol = session["breath"]
    memory: MemoryEngine = session["memory"]

    signals = extract_rhythm_signals(body.get("marks", []))
    output = engine.rhythm_step(signals)
    pulse = breath_proto.force_pulse(engine.state.breath)

    # content-free friction logging: pressure only, no summary text
    k = engine.state.kernel
    hesitation = "STRONG" if output.pip_active else ("MILD" if k.pressure > 0.5 else "NONE")
    memory.log(
        pressure=k.pressure,
        hesitation=hesitation,
        summary="",
        tick=engine.state.tick,
        tone=None,
        rhythm=signals.rhythm,
    )

    return jsonify({
        "breath": {
            "state": pulse.state.value,
            "icon": pulse.icon,
            "haptic": pulse.haptic_pattern,
            "interval": pulse.interval_seconds,
        },
        "pip_active": output.pip_active,
        "anchor": output.anchor,
        "weather": output.weather,
        "oscillator_mode": output.oscillator_mode,
        "snapshot": engine.state.snapshot(),
    })


@app.route("/weather", methods=["GET"])
def weather():
    """Parent mode: weather only, no content."""
    sid = request.args.get("session_id", "")
    if sid not in _sessions:
        return jsonify({"error": "unknown session"}), 404
    engine: SpiralEngine = _sessions[sid]["engine"]
    return jsonify({"weather": engine.get_weather()})


@app.route("/peek")
def peek():
    """Parent Peek — weather only. Never the marks."""
    return render_template("peek.html")


@app.route("/weather/current", methods=["GET"])
def weather_current():
    """Weather of the most recent kid session. No ids, no content, no history.

    Parents never see the child's marks — only three words of system
    weather. When no instrument is open, the sky is simply quiet.
    """
    latest = None
    latest_start = -1.0
    for session in _sessions.values():
        engine: SpiralEngine = session["engine"]
        if engine.state.context.T.mode != SessionMode.KID:
            continue
        if engine.state.session_start > latest_start:
            latest_start = engine.state.session_start
            latest = engine
    if latest is None:
        return jsonify({"present": False, "weather": None})
    return jsonify({"present": True, "weather": latest.get_weather()})


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


@app.route("/music/list", methods=["GET"])
def music_list():
    """List the household's dropped-in music. Filenames only — no metadata
    scraping, no durations, no analysis."""
    tracks = [
        {"id": p.name, "title": p.stem}
        for p in _scan_music()
    ]
    return jsonify({"tracks": tracks})


@app.route("/music/file/<path:track_id>")
def music_file(track_id: str):
    """Serve one dropped-in track. The id must match a scanned filename
    exactly — no traversal, no guessing."""
    valid = {p.name for p in _scan_music()}
    if track_id not in valid:
        return jsonify({"error": "unknown track"}), 404
    return send_from_directory(_music_dir(), track_id)


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
# Bridge endpoints — PipV0 <-> Fairyland
# ---------------------------------------------------------------------------

@app.route("/bridge/friction", methods=["GET"])
def bridge_friction():
    """Extract friction summary from a session for PipV0's weekly cycle."""
    sid = request.args.get("session_id", "")
    if sid not in _sessions:
        return jsonify({"error": "unknown session"}), 404
    session = _sessions[sid]
    summary = extract_session_friction(sid, session["engine"], session["memory"])
    events = friction_to_pip_events(summary)
    return jsonify({
        "session_id": summary.session_id,
        "tick_count": summary.tick_count,
        "avg_pressure": round(summary.avg_pressure, 3),
        "max_pressure": round(summary.max_pressure, 3),
        "dominant_tone": summary.dominant_tone,
        "hesitation_count": summary.hesitation_count,
        "drift_scores": summary.drift_scores,
        "pip_events": events,
    })


@app.route("/bridge/governor", methods=["GET"])
def bridge_governor():
    """Get Token Governor state and its reveal speed mapping."""
    if not PIP_DATA_DIR:
        return jsonify({"error": "PIP_DATA_DIR not configured"}), 400
    gov_path = str(Path(PIP_DATA_DIR) / "token_governor_state.json")
    gov = load_governor_state(gov_path)
    return jsonify({
        "mode": gov.mode,
        "daily_budget": gov.daily_budget,
        "daily_used": gov.daily_used,
        "remaining_ratio": round(gov.budget_remaining_ratio, 3),
        "reveal_speed": governor_to_reveal_speed(gov),
    })


@app.route("/bridge/thermal", methods=["GET"])
def bridge_thermal():
    """Get PipV0's latest thermal state."""
    if not PIP_DATA_DIR:
        return jsonify({"error": "PIP_DATA_DIR not configured"}), 400
    thermal_path = str(Path(PIP_DATA_DIR) / "s25_latest_dream.json")
    thermal = load_pip_thermal(thermal_path)
    if not thermal:
        return jsonify({"error": "no thermal data"}), 404
    return jsonify({
        "coherence": round(thermal.coherence, 3),
        "pressure": round(thermal.pressure, 3),
        "drift": round(thermal.drift, 3),
        "groove": round(thermal.groove, 3),
        "integration_debt": round(thermal.integration_debt, 3),
        "scar": round(thermal.scar, 3),
    })


@app.route("/bridge/status", methods=["GET"])
def bridge_status():
    """Bridge health — is PipV0 connected?"""
    connected = bool(PIP_DATA_DIR and Path(PIP_DATA_DIR).exists())
    thermal_exists = connected and (Path(PIP_DATA_DIR) / "s25_latest_dream.json").exists()
    gov_exists = connected and (Path(PIP_DATA_DIR) / "token_governor_state.json").exists()
    return jsonify({
        "pip_connected": connected,
        "pip_dir": PIP_DATA_DIR,
        "thermal_available": thermal_exists,
        "governor_available": gov_exists,
        "active_sessions": len(_sessions),
    })


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def create_app():
    return app


if __name__ == "__main__":
    app.run(debug=True, port=5000)
