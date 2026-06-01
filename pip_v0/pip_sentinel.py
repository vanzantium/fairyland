"""
pip_sentinel.py — Behavioral fingerprint and unauthorized-use detection.

Because Pip tunes to one user, deviation from that user's rhythm IS the
security signal. An intruder types at a different cadence, works different
hours, and asks for different things. The sentinel learns the owner's
fingerprint and raises the security posture when behavior drifts.

Design principles (matching the rest of the build):
  - Privacy-preserving: stores compressed statistics, never raw activity logs.
  - Local only: the fingerprint never leaves the machine. No phone-home.
  - Graduated response: escalate posture, don't slam a lockout on a bad guess.
  - Poison-resistant: only learn from CALM/WATCH sessions, so an intruder
    cannot slowly drag the baseline toward themselves.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from . import pip_config


# Posture ladder — graduated, not binary.
POSTURE_CALM = "CALM"     # normal owner; autonomous + bridge work allowed
POSTURE_WATCH = "WATCH"   # mild drift; log it, keep going
POSTURE_GUARD = "GUARD"   # real drift; pause autonomy, confirm sensitive actions
POSTURE_LOCK = "LOCK"     # extreme drift; freeze autonomy, require re-auth

# Anomaly thresholds (0..1)
WATCH_AT = 0.35
GUARD_AT = 0.6
LOCK_AT = 0.82

# How fast the baseline adapts to the owner (EMA weight for new data).
LEARN_RATE = 0.12


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Fingerprint:
    """Compressed behavioral signature of the owner."""
    # Histogram of activity by hour of day (24 buckets, normalized lazily).
    active_hours: list[float] = field(default_factory=lambda: [0.0] * 24)
    # Rolling cadence: mean + variance of seconds between user actions.
    cadence_mean_s: float = 0.0
    cadence_var_s: float = 0.0
    # Distribution over which personas/tools the owner uses.
    persona_usage: dict[str, float] = field(default_factory=dict)
    # Typical task shape.
    task_len_mean: float = 0.0
    task_len_var: float = 0.0
    # Common command verbs the owner uses (hashed bag, capped).
    verb_weights: dict[str, float] = field(default_factory=dict)
    # Bookkeeping.
    samples: int = 0
    updated_at: str = ""

    def is_cold(self) -> bool:
        """True until we have enough samples to judge anything."""
        return self.samples < 8


@dataclass
class SentinelState:
    fingerprint: Fingerprint = field(default_factory=Fingerprint)
    posture: str = POSTURE_CALM
    last_anomaly: float = 0.0
    last_assessment: Optional[dict[str, Any]] = None
    flags: list[dict[str, Any]] = field(default_factory=list)
    consecutive_anomalies: int = 0


# Lightweight, privacy-preserving verb extraction.
_COMMON_VERBS = {
    "build", "fix", "write", "read", "check", "run", "test", "make",
    "find", "search", "summarize", "review", "refactor", "explain",
    "open", "close", "send", "draft", "plan", "clean", "update", "add",
    "remove", "show", "list", "scan", "import", "export", "save", "load",
}


def state_path() -> Path:
    return pip_config.get_memory_path() / "sentinel_fingerprint.json"


def load_state() -> SentinelState:
    path = state_path()
    if not path.exists():
        return SentinelState()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        fp_data = data.get("fingerprint", {})
        fp = Fingerprint(
            active_hours=fp_data.get("active_hours", [0.0] * 24),
            cadence_mean_s=fp_data.get("cadence_mean_s", 0.0),
            cadence_var_s=fp_data.get("cadence_var_s", 0.0),
            persona_usage=fp_data.get("persona_usage", {}),
            task_len_mean=fp_data.get("task_len_mean", 0.0),
            task_len_var=fp_data.get("task_len_var", 0.0),
            verb_weights=fp_data.get("verb_weights", {}),
            samples=fp_data.get("samples", 0),
            updated_at=fp_data.get("updated_at", ""),
        )
        if len(fp.active_hours) != 24:
            fp.active_hours = (fp.active_hours + [0.0] * 24)[:24]
        return SentinelState(
            fingerprint=fp,
            posture=data.get("posture", POSTURE_CALM),
            last_anomaly=data.get("last_anomaly", 0.0),
            last_assessment=data.get("last_assessment"),
            flags=data.get("flags", [])[-50:],
            consecutive_anomalies=data.get("consecutive_anomalies", 0),
        )
    except Exception:
        return SentinelState()


def save_state(state: SentinelState) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    state.flags = state.flags[-50:]
    payload = {
        "fingerprint": asdict(state.fingerprint),
        "posture": state.posture,
        "last_anomaly": round(state.last_anomaly, 4),
        "last_assessment": state.last_assessment,
        "flags": state.flags,
        "consecutive_anomalies": state.consecutive_anomalies,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Observation extraction
# ---------------------------------------------------------------------------

def _extract_verbs(task: str) -> dict[str, float]:
    weights: dict[str, float] = {}
    for word in (task or "").lower().split():
        clean = "".join(c for c in word if c.isalpha())
        if clean in _COMMON_VERBS:
            weights[clean] = weights.get(clean, 0.0) + 1.0
    return weights


def _normalize(hist: list[float]) -> list[float]:
    total = sum(hist)
    if total <= 0:
        return [0.0] * len(hist)
    return [h / total for h in hist]


def _dist_distance(a: dict[str, float], b: dict[str, float]) -> float:
    """L1 distance between two normalized distributions (0..1)."""
    if not a and not b:
        return 0.0
    ta, tb = sum(a.values()) or 1.0, sum(b.values()) or 1.0
    keys = set(a) | set(b)
    diff = sum(abs(a.get(k, 0.0) / ta - b.get(k, 0.0) / tb) for k in keys)
    return min(1.0, diff / 2.0)


def _z_to_score(value: float, mean: float, var: float) -> float:
    """Map a deviation to 0..1 via a soft sigmoid on the z-score."""
    std = math.sqrt(var) if var > 1e-9 else 0.0
    if std < 1e-6:
        # No spread learned yet — treat large absolute gaps gently.
        gap = abs(value - mean)
        scale = abs(mean) + 1.0
        return min(1.0, gap / (scale * 3.0))
    z = abs(value - mean) / std
    # z of ~3 ≈ strong anomaly
    return 1.0 / (1.0 + math.exp(-(z - 2.0)))


# ---------------------------------------------------------------------------
# Core: observe + assess
# ---------------------------------------------------------------------------

def assess(
    persona: str = "",
    task: str = "",
    interval_s: float | None = None,
    hour: int | None = None,
    state: SentinelState | None = None,
) -> dict[str, Any]:
    """
    Compare one observation against the owner's fingerprint.

    Returns an assessment with an anomaly score and recommended posture.
    Does NOT mutate the baseline — call observe() to learn.
    """
    st = state or load_state()
    fp = st.fingerprint
    now_hour = hour if hour is not None else datetime.now().hour

    if fp.is_cold():
        return {
            "anomaly": 0.0,
            "posture": POSTURE_CALM,
            "cold_start": True,
            "samples": fp.samples,
            "reason": "Still learning the owner's rhythm.",
            "dimensions": {},
        }

    dims: dict[str, float] = {}

    # 1. Active hours — how unusual is this hour for the owner?
    hist = _normalize(fp.active_hours)
    expected = hist[now_hour]
    peak = max(hist) if hist else 0.0
    dims["hour"] = 0.0 if peak <= 0 else min(1.0, max(0.0, (peak - expected) / peak))

    # 2. Cadence — typing/action rhythm.
    if interval_s is not None and fp.samples > 3:
        dims["cadence"] = _z_to_score(interval_s, fp.cadence_mean_s, fp.cadence_var_s)

    # 3. Persona usage — does the owner use this tool?
    if persona:
        owner_dist = fp.persona_usage
        obs = {persona: 1.0}
        dims["persona"] = _dist_distance(obs, owner_dist)

    # 4. Task length — does the owner phrase tasks this way?
    if task:
        dims["task_len"] = _z_to_score(
            float(len(task)), fp.task_len_mean, fp.task_len_var
        )
        # 5. Vocabulary — do the command verbs match the owner's?
        obs_verbs = _extract_verbs(task)
        if obs_verbs or fp.verb_weights:
            dims["vocab"] = _dist_distance(obs_verbs, fp.verb_weights)

    # Combine — weighted, robust to missing dimensions.
    weights = {
        "hour": 0.20, "cadence": 0.25, "persona": 0.20,
        "task_len": 0.15, "vocab": 0.20,
    }
    present = {k: v for k, v in dims.items() if k in weights}
    if present:
        wsum = sum(weights[k] for k in present)
        anomaly = sum(present[k] * weights[k] for k in present) / wsum
    else:
        anomaly = 0.0

    posture = _posture_for(anomaly, st.consecutive_anomalies)

    return {
        "anomaly": round(anomaly, 4),
        "posture": posture,
        "cold_start": False,
        "samples": fp.samples,
        "dimensions": {k: round(v, 4) for k, v in dims.items()},
        "reason": _reason_for(posture, dims),
    }


def observe(
    persona: str = "",
    task: str = "",
    interval_s: float | None = None,
    hour: int | None = None,
    state: SentinelState | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """
    Record one observation: assess it, update posture, and — only if the
    session looks like the owner — fold it into the baseline fingerprint.
    """
    st = state or load_state()
    assessment = assess(persona, task, interval_s, hour, st)
    anomaly = assessment["anomaly"]
    computed = assessment["posture"]

    # Sticky posture: once GUARD/LOCK, a calm-looking next message must NOT
    # silently de-escalate. Posture can only rise here; only an explicit
    # owner reauthorize() brings it back down. This stops an intruder from
    # tripping the alarm and then "behaving" to slip back to CALM.
    posture = _max_posture(st.posture, computed)

    st.last_anomaly = anomaly
    st.last_assessment = assessment
    st.posture = posture

    if computed in (POSTURE_GUARD, POSTURE_LOCK):
        st.consecutive_anomalies += 1
        st.flags.append({
            "at": utc_now(),
            "anomaly": round(anomaly, 4),
            "posture": posture,
            "persona": persona,
            "dimensions": assessment.get("dimensions", {}),
        })
    elif computed == POSTURE_CALM and posture == POSTURE_CALM:
        st.consecutive_anomalies = 0

    # Poison resistance: only learn when BOTH the latest read and the held
    # posture look like the owner. A held GUARD/LOCK freezes learning.
    learn = (computed in (POSTURE_CALM, POSTURE_WATCH)
             and posture in (POSTURE_CALM, POSTURE_WATCH))
    if learn:
        _fold_into_fingerprint(st.fingerprint, persona, task, interval_s, hour)

    if persist:
        save_state(st)

    return {
        **assessment,
        "posture": posture,          # held (sticky) posture, not just this read
        "computed_posture": computed,
        "learned": learn,
        "consecutive_anomalies": st.consecutive_anomalies,
    }


def _fold_into_fingerprint(
    fp: Fingerprint,
    persona: str,
    task: str,
    interval_s: float | None,
    hour: int | None,
) -> None:
    h = hour if hour is not None else datetime.now().hour
    fp.active_hours[h] += 1.0

    if interval_s is not None:
        if fp.samples == 0:
            fp.cadence_mean_s = interval_s
            fp.cadence_var_s = 0.0
        else:
            delta = interval_s - fp.cadence_mean_s
            fp.cadence_mean_s += LEARN_RATE * delta
            fp.cadence_var_s = (1 - LEARN_RATE) * (fp.cadence_var_s + LEARN_RATE * delta * delta)

    if persona:
        for k in fp.persona_usage:
            fp.persona_usage[k] *= (1 - LEARN_RATE)
        fp.persona_usage[persona] = fp.persona_usage.get(persona, 0.0) + 1.0

    if task:
        tlen = float(len(task))
        if fp.samples == 0:
            fp.task_len_mean = tlen
            fp.task_len_var = 0.0
        else:
            delta = tlen - fp.task_len_mean
            fp.task_len_mean += LEARN_RATE * delta
            fp.task_len_var = (1 - LEARN_RATE) * (fp.task_len_var + LEARN_RATE * delta * delta)

        for verb, w in _extract_verbs(task).items():
            for k in list(fp.verb_weights):
                fp.verb_weights[k] *= (1 - LEARN_RATE * 0.5)
            fp.verb_weights[verb] = fp.verb_weights.get(verb, 0.0) + w
        # Cap vocabulary size to keep it compressed.
        if len(fp.verb_weights) > 40:
            top = sorted(fp.verb_weights.items(), key=lambda kv: kv[1], reverse=True)[:40]
            fp.verb_weights = dict(top)

    fp.samples += 1
    fp.updated_at = utc_now()


_POSTURE_RANK = {
    POSTURE_CALM: 0, POSTURE_WATCH: 1, POSTURE_GUARD: 2, POSTURE_LOCK: 3,
}


def _max_posture(a: str, b: str) -> str:
    """Return the more severe of two postures."""
    return a if _POSTURE_RANK.get(a, 0) >= _POSTURE_RANK.get(b, 0) else b


def _posture_for(anomaly: float, consecutive: int) -> str:
    base = POSTURE_CALM
    if anomaly >= LOCK_AT:
        base = POSTURE_LOCK
    elif anomaly >= GUARD_AT:
        base = POSTURE_GUARD
    elif anomaly >= WATCH_AT:
        base = POSTURE_WATCH
    # Repeated guard-level anomalies escalate to lock.
    if base == POSTURE_GUARD and consecutive >= 2:
        return POSTURE_LOCK
    return base


def _reason_for(posture: str, dims: dict[str, float]) -> str:
    if posture == POSTURE_CALM:
        return "Behavior matches the owner's rhythm."
    worst = max(dims.items(), key=lambda kv: kv[1], default=("", 0.0))
    names = {
        "hour": "active at an unusual hour",
        "cadence": "typing/action rhythm is off",
        "persona": "using an unfamiliar tool",
        "task_len": "tasks phrased unusually",
        "vocab": "unfamiliar command vocabulary",
    }
    detail = names.get(worst[0], "behavior drifted")
    if posture == POSTURE_LOCK:
        return f"Strong mismatch — {detail}. Freezing autonomous actions."
    if posture == POSTURE_GUARD:
        return f"Notable mismatch — {detail}. Pausing autonomy, confirm sensitive actions."
    return f"Mild drift — {detail}. Watching."


# ---------------------------------------------------------------------------
# Gate — the single call other modules use before autonomous/bridge work
# ---------------------------------------------------------------------------

def autonomy_allowed(state: SentinelState | None = None) -> bool:
    """True if the current posture permits autonomous / bridge work."""
    st = state or load_state()
    return st.posture in (POSTURE_CALM, POSTURE_WATCH)


def reauthorize(state: SentinelState | None = None) -> dict[str, Any]:
    """
    Owner confirms identity — reset posture to CALM and clear the streak.
    Call this from an explicit, user-driven action (not autonomously).
    """
    st = state or load_state()
    st.posture = POSTURE_CALM
    st.consecutive_anomalies = 0
    st.flags.append({"at": utc_now(), "event": "reauthorized_by_owner"})
    save_state(st)
    return {"ok": True, "posture": st.posture}


def status() -> dict[str, Any]:
    st = load_state()
    fp = st.fingerprint
    return {
        "posture": st.posture,
        "last_anomaly": round(st.last_anomaly, 4),
        "autonomy_allowed": st.posture in (POSTURE_CALM, POSTURE_WATCH),
        "cold_start": fp.is_cold(),
        "samples": fp.samples,
        "consecutive_anomalies": st.consecutive_anomalies,
        "recent_flags": st.flags[-5:],
        "last_assessment": st.last_assessment,
    }
