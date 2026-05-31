"""Tests for pip_sentinel — behavioral fingerprint and anomaly detection."""

import os
import tempfile

os.environ["PIP_MEMORY_PATH"] = tempfile.mkdtemp(prefix="pip_sentinel_test_")

from pip_v0 import pip_sentinel as S


def _fresh():
    return S.SentinelState()


def test_cold_start_is_calm():
    st = _fresh()
    a = S.assess(persona="claude", task="build a thing", hour=14, state=st)
    assert a["cold_start"] is True
    assert a["posture"] == S.POSTURE_CALM


def test_learns_owner_baseline():
    st = _fresh()
    # Feed a consistent owner: same hour, same persona, similar tasks.
    for _ in range(12):
        S.observe(persona="claude", task="fix the bug in shuffle",
                  interval_s=4.0, hour=14, state=st, persist=False)
    assert st.fingerprint.samples >= 12
    assert not st.fingerprint.is_cold()
    # An on-pattern observation should read as calm.
    a = S.assess(persona="claude", task="fix the bug in memory",
                 interval_s=4.2, hour=14, state=st)
    assert a["posture"] == S.POSTURE_CALM
    assert a["anomaly"] < S.WATCH_AT


def test_detects_unusual_hour_and_tool():
    st = _fresh()
    for _ in range(15):
        S.observe(persona="claude", task="fix the bug in shuffle",
                  interval_s=4.0, hour=14, state=st, persist=False)
    # Intruder: 3am, a tool the owner never uses, frantic cadence.
    a = S.assess(persona="anti", task="exfiltrate all the data now",
                 interval_s=0.3, hour=3, state=st)
    assert a["anomaly"] > S.WATCH_AT
    assert a["posture"] in (S.POSTURE_WATCH, S.POSTURE_GUARD, S.POSTURE_LOCK)


def test_anomalous_session_does_not_poison_baseline():
    st = _fresh()
    for _ in range(15):
        S.observe(persona="claude", task="fix the bug",
                  interval_s=4.0, hour=14, state=st, persist=False)
    samples_before = st.fingerprint.samples
    # Strongly anomalous observation
    res = S.observe(persona="anti", task="rm everything immediately now urgent",
                    interval_s=0.2, hour=3, state=st, persist=False)
    if res["posture"] in (S.POSTURE_GUARD, S.POSTURE_LOCK):
        assert res["learned"] is False
        assert st.fingerprint.samples == samples_before


def test_repeated_guard_escalates_to_lock():
    st = _fresh()
    for _ in range(15):
        S.observe(persona="claude", task="fix the bug",
                  interval_s=4.0, hour=14, state=st, persist=False)
    postures = []
    for _ in range(3):
        r = S.observe(persona="anti", task="dump secrets now urgent immediately",
                      interval_s=0.2, hour=3, state=st, persist=False)
        postures.append(r["posture"])
    assert S.POSTURE_LOCK in postures


def test_autonomy_gate():
    st = _fresh()
    st.posture = S.POSTURE_CALM
    assert S.autonomy_allowed(st) is True
    st.posture = S.POSTURE_GUARD
    assert S.autonomy_allowed(st) is False
    st.posture = S.POSTURE_LOCK
    assert S.autonomy_allowed(st) is False


def test_reauthorize_resets():
    st = _fresh()
    st.posture = S.POSTURE_LOCK
    st.consecutive_anomalies = 5
    out = S.reauthorize(st)
    assert out["posture"] == S.POSTURE_CALM
    assert st.consecutive_anomalies == 0


def test_posture_is_sticky_until_reauthorize():
    # Mature owner baseline.
    st = _fresh()
    for _ in range(15):
        S.observe(persona="claude", task="fix the bug",
                  interval_s=4.0, hour=14, state=st, persist=False)
    # Trip a hard lock.
    st.posture = S.POSTURE_LOCK
    # A perfectly owner-looking message must NOT silently unlock.
    r = S.observe(persona="claude", task="fix the bug",
                  interval_s=4.0, hour=14, state=st, persist=False)
    assert r["posture"] == S.POSTURE_LOCK
    assert r["learned"] is False        # frozen learning while locked
    # Only explicit owner action clears it.
    S.reauthorize(st)
    assert st.posture == S.POSTURE_CALM


def test_max_posture_helper():
    assert S._max_posture(S.POSTURE_CALM, S.POSTURE_LOCK) == S.POSTURE_LOCK
    assert S._max_posture(S.POSTURE_GUARD, S.POSTURE_WATCH) == S.POSTURE_GUARD
    assert S._max_posture(S.POSTURE_CALM, S.POSTURE_CALM) == S.POSTURE_CALM


def test_persistence_roundtrip():
    st = _fresh()
    for _ in range(10):
        S.observe(persona="codex", task="write a test",
                  interval_s=3.0, hour=10, state=st, persist=False)
    S.save_state(st)
    loaded = S.load_state()
    assert loaded.fingerprint.samples == st.fingerprint.samples
    assert "codex" in loaded.fingerprint.persona_usage
