# Fairyland

*A non-extractive digital ecology.*

> Feeling precedes information. Context precedes content.  
> Authority is never outsourced to the system.

---

## What it is

Fairyland is a Python/Flask engine for building digital experiences that are **regulated, not optimising**. It tracks internal state — pressure, coherence, reserve, groove — and uses that state to pace, slow, or reorient interactions before they overshoot.

It is built for contexts where the usual design assumptions (engagement maximisation, persistent identity, session memory) are the problem rather than the goal.

---

## Core design principles

- **No user tracking. No accounts. No analytics.** Sessions are ephemeral by default. The burn endpoint deletes them entirely.
- **Memory is compression, not storage.** Raw interaction history is burned. Only high-friction moments are compressed into tattoos. The nightly dwell cycle distills patterns — not logs.
- **Drift is watched, not banned.** Parasocial attachment, echo loops, and narrowing attention are tracked and interrupted with sideways content (humor, mundane observations, redirects) rather than blocks.
- **Authority stays with the person.** The system never claims expertise in foraging, medicine, identification, or location. It supports attention, not decisions.

---

## Architecture

```
fairyland/
├── app.py                  — Flask API (ephemeral sessions, no persistence by default)
├── engine/
│   ├── spiral.py           — Spiral Engine: HANDSHAKE → ANCHOR → HOLD → RENDER → RITUAL
│   ├── state.py            — KernelState, OscillatorState, three-register context (t), (.), (T)
│   ├── drift.py            — Bias drift tracker: parasocial, echo, narrowing
│   ├── oscillator.py       — Phi-driven mode cycling: BUILD / AUDIT / DWELL / SHED
│   ├── sensing.py          — Rich text signal extraction: tone, rhythm, repetition, trajectory
│   ├── healing.py          — Micro-interventions triggered at high pressure
│   └── shuffle.py          — Proper Shuffle: silence-aware playlist sequencing
├── memory/
│   ├── engine.py           — Friction log + dwell cycle: tattoo compression
│   └── tiered.py           — Tiered memory bridge (fur / skin / tattoo layers from PipV0)
├── beacon/
│   └── mesh.py             — Beacon broadcast + handshake: regulatory mesh between instances
├── breath/
│   └── protocol.py         — Breath protocol: CALM / FLOW / EDGE / OVERDRIVE pacing
├── bridge.py               — PipV0 to Fairyland integration layer
├── data/
│   └── plants/             — Plant card data (field-guide reference, not identification)
└── templates/
    └── index.html          — Minimal front-end shell
```

---

## Spiral Engine

The core regulatory loop. Moves through five states on each tick:

```
HANDSHAKE -> ANCHOR -> HOLD -> RENDER -> RITUAL -> (loop)
```

Driven by:

- **KernelState** — reserve, recovery, stress, pressure, groove, coherence
- **OscillatorState** — phi phase cycling through BUILD / AUDIT / DWELL / SHED modes
- **Three-register context** — `(t)` micro rhythm, `(.)` pip/pause hold, `(T)` macro arc
- **Breath** — involuntary metronome: CALM (6-7 s), FLOW (4-5 s), EDGE (2-3 s), OVERDRIVE (silence)
- **DriftTracker** — parasocial, echo, and narrowing scores with cooldown-gated sideways nudges

Session modes: `KID`, `ADULT`, `CODER`. Each adjusts safety flags and pressure thresholds.

---

## Safety

See [`SAFETY.md`](SAFETY.md) for the prime directive.

Short version:
- No foraging, medicinal, dosage, or "is it edible?" guidance — ever
- No GPS or precise coordinates — archetypes and habitat only
- Kid mode routes to external identification resources, never the engine itself
- No user tracking, no accounts, no analytics
- Burn mode is the default: sessions end with all raw history deleted

---

## Getting started

```bash
pip install -r requirements.txt
python -m fairyland.app
```

Or with Gunicorn:

```bash
gunicorn "fairyland.app:create_app()"
```

Optional environment variables:

```bash
FAIRYLAND_TATTOO_DIR=/path/to/tattoos   # persist compressed tattoos across sessions
FAIRYLAND_PIP_DIR=/path/to/pip-data    # connect PipV0 thermal and governor state
```

Without these, Fairyland runs fully ephemerally with no disk writes.

---

## API

All endpoints return JSON. Sessions are identified by a short hex `session_id`.

### Core

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Service health check |
| `POST` | `/session` | Create ephemeral session. Body: `{"mode": "ADULT"}` |
| `POST` | `/step` | Send text through the Spiral Engine. Body: `{"session_id": "...", "text": "..."}` |
| `GET` | `/weather?session_id=` | Parent/weather-only mode — weather state, no content |
| `GET` | `/drift?session_id=` | Drift HUD: parasocial, echo, narrowing scores |
| `POST` | `/burn` | Delete session. Only tattoos optionally survive |
| `POST` | `/dwell` | Nightly dwell cycle — compress friction logs into tattoos |
| `GET` | `/beacon?session_id=` | Beacon broadcast for the regulatory mesh |
| `POST` | `/handshake` | Test handshake compatibility between two beacon states |

### Shuffle

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/shuffle/start` | Start a Proper Shuffle session with a playlist |
| `POST` | `/shuffle/next` | Next track, silence window, or exit cue |

### Reference data

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/plant/<species>` | Plant card data (field-guide reference, not identification) |

### PipV0 bridge *(requires `FAIRYLAND_PIP_DIR`)*

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/bridge/friction?session_id=` | Extract session friction as PipV0 usage events |
| `GET` | `/bridge/governor` | Token Governor state and reveal-speed mapping |
| `GET` | `/bridge/thermal` | PipV0 latest thermal state (coherence, pressure, drift, groove) |
| `GET` | `/bridge/status` | Bridge health check |

---

## `/step` response shape

```json
{
  "text": "...",
  "state": "ANCHOR",
  "breath": {
    "state": "FLOW",
    "icon": "~",
    "haptic": "gentle_wave",
    "interval": 4.5
  },
  "anchor": "...",
  "pip_active": false,
  "ritual_question": null,
  "weather": "settling",
  "snapshot": {
    "spiral": "ANCHOR",
    "coherence": 0.87,
    "pressure": 0.12,
    "groove": 0.61,
    "oscillator_mode": "BUILD",
    "tick": 3
  },
  "signals": {
    "tone": "curious",
    "rhythm": "steady",
    "repetition": 0.1,
    "trajectory": "opening"
  }
}
```

---

## Running tests

```bash
pytest tests/
```

Covers: Spiral Engine, memory compression, drift tracker, oscillator, sensing, beacon mesh, shuffle, breath protocol, healing, and the PipV0 bridge layer.

---

## What it is not

- Not a chatbot
- Not an LLM wrapper
- Not a recommendation engine
- Not a surveillance tool

It is a regulatory layer. A system that tracks its own internal state and uses that state to moderate its own outputs before they reach a person.

---

## License

MIT
