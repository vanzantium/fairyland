"""Tests for pip_bridge_jobs — background bridge execution gated by sentinel."""

import os
import tempfile
import time

os.environ["PIP_MEMORY_PATH"] = tempfile.mkdtemp(prefix="pip_bridgejobs_test_")

from pip_v0 import pip_bridge_jobs as BJ
from pip_v0 import pip_sentinel as S
from pip_v0 import pip_text_bridge


def _force_posture(posture: str):
    st = S.load_state()
    st.posture = posture
    S.save_state(st)


def test_sentinel_blocks_when_guarded():
    _force_posture(S.POSTURE_GUARD)
    out = BJ.queue_bridge_task("claude", "do something")
    assert out["ok"] is False
    assert out["blocked"] is True
    assert out["reason"] == "sentinel_posture"


def test_bridge_task_runs_when_calm(monkeypatch):
    _force_posture(S.POSTURE_CALM)

    # Stub the actual typing so the test never touches a real screen.
    def fake_send(persona, task, response_wait_s=None):
        return pip_text_bridge.BridgeResult(
            ok=True, persona=persona, task=task,
            response="stubbed response", elapsed_s=0.1,
            harvest_method="clipboard_auto",
        )

    monkeypatch.setattr(pip_text_bridge, "send", fake_send)

    job = BJ.queue_bridge_task("claude", "summarize the readme")
    assert "id" in job

    # Wait for the daemon thread to finish.
    job_id = job["id"]
    for _ in range(50):
        res = BJ.get_result(job_id)
        if res:
            break
        time.sleep(0.05)

    res = BJ.get_result(job_id)
    assert res is not None
    assert res["ok"] is True
    assert res["response"] == "stubbed response"


def test_bypass_sentinel_flag():
    _force_posture(S.POSTURE_LOCK)
    out = BJ.queue_bridge_task("claude", "x", bypass_sentinel=True)
    # With bypass, it should start a job (returns a job dict with id), not block.
    assert "id" in out or out.get("blocked") is None


def test_self_improving_task_blocked_when_locked():
    _force_posture(S.POSTURE_LOCK)
    out = BJ.queue_self_improving_task("codex", "write a test")
    assert out["ok"] is False
    assert out["blocked"] is True


def test_self_improving_task_runs(monkeypatch):
    _force_posture(S.POSTURE_CALM)

    def fake_send(persona, task, response_wait_s=None):
        return pip_text_bridge.BridgeResult(
            ok=True, persona=persona, task=task,
            response="def go(): pass\nif not x: return",
            elapsed_s=0.1, harvest_method="clipboard_auto",
        )

    monkeypatch.setattr(pip_text_bridge, "send", fake_send)

    job = BJ.queue_self_improving_task(
        "codex", "write a function go", use_local_model=False, max_attempts=1,
    )
    assert "id" in job

    job_id = job["id"]
    for _ in range(60):
        res = BJ.get_result(job_id)
        if res:
            break
        time.sleep(0.05)

    res = BJ.get_result(job_id)
    assert res is not None
    assert res["kind"] == "self_improving_task"
    assert "score" in res


def test_status_reports_posture():
    _force_posture(S.POSTURE_CALM)
    st = BJ.status()
    assert "bridge_autonomy_allowed" in st
    assert "sentinel_posture" in st
    assert "strategy_memory" in st
