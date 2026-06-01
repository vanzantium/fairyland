"""
pip_bridge_jobs.py — Run text-bridge tasks in the background.

This is what lets Pip work like Codex/Cursor's background agents, but
through the clipboard text bridge instead of a paid API: she queues a
task, types it into the tool window when the keyboard is free, harvests
the response, and reports back — without blocking the user.

Two honest constraints, handled here:
  1. Only ONE bridge task can type at a time (one keyboard, one clipboard).
     A lock serializes them.
  2. Typing steals focus, so bridge jobs should run when the user is idle.
     The sentinel gates this: bridge work only runs at CALM/WATCH posture.

A background job can either:
  - run a single bridge send (queue_bridge_task), or
  - run the self-improving loop over the bridge (queue_self_improving_task),
    where Pip's small model decomposes the task and scores the tool's reply.
"""
from __future__ import annotations

import json
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from . import pip_config
from . import pip_jobs
from . import pip_sentinel
from . import pip_text_bridge


# Serialize all bridge typing — one keyboard, one clipboard.
_BRIDGE_LOCK = threading.Lock()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def results_path() -> Path:
    return pip_config.get_memory_path() / "bridge_results.json"


def _read_results() -> dict[str, Any]:
    path = results_path()
    if not path.exists():
        return {"results": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"results": []}


def _write_result(entry: dict[str, Any]) -> None:
    data = _read_results()
    data.setdefault("results", []).append(entry)
    data["results"] = data["results"][-50:]
    results_path().write_text(json.dumps(data, indent=2), encoding="utf-8")


def list_results() -> list[dict[str, Any]]:
    return _read_results().get("results", [])


def get_result(job_id: str) -> Optional[dict[str, Any]]:
    for r in _read_results().get("results", []):
        if r.get("job_id") == job_id:
            return r
    return None


# ---------------------------------------------------------------------------
# Single bridge task as a background job
# ---------------------------------------------------------------------------

def queue_bridge_task(
    persona: str,
    task: str,
    wait_s: float | None = None,
    bypass_sentinel: bool = False,
) -> dict[str, Any]:
    """
    Queue a single text-bridge send as a background job.

    Returns the job record immediately; the result lands in bridge_results.json
    (and is retrievable via get_result(job_id)).
    """
    if not bypass_sentinel and not pip_sentinel.autonomy_allowed():
        st = pip_sentinel.status()
        return {
            "ok": False,
            "blocked": True,
            "reason": "sentinel_posture",
            "posture": st["posture"],
            "message": f"Bridge work paused — security posture is {st['posture']}. "
                       f"Owner re-authorization required.",
        }

    def run(job_id: str) -> str:
        with _BRIDGE_LOCK:
            pip_jobs.append_log(job_id, f"Bridge → {persona}: {task[:60]}")
            result = pip_text_bridge.send(persona, task, response_wait_s=wait_s)
            entry = {
                "job_id": job_id,
                "kind": "bridge_task",
                "persona": result.persona,
                "task": task,
                "ok": result.ok,
                "response": result.response,
                "response_length": len(result.response),
                "elapsed_s": result.elapsed_s,
                "needs_manual_copy": result.needs_manual_copy,
                "harvest_method": result.harvest_method,
                "error": result.error,
                "finished_at": utc_now(),
            }
            _write_result(entry)
            if result.ok and not result.needs_manual_copy:
                pip_jobs.append_log(job_id, f"Harvested {len(result.response)} chars.")
                return f"ok: {len(result.response)} chars"
            if result.needs_manual_copy:
                pip_jobs.append_log(job_id, "Sent, awaiting manual copy of response.")
                return "sent: needs manual harvest"
            pip_jobs.append_log(job_id, f"Failed: {result.error}")
            return f"failed: {result.error}"

    return pip_jobs.start_job(
        "bridge_task",
        f"{persona}: {task[:70]}",
        run,
        details={"persona": persona, "task": task},
    )


# ---------------------------------------------------------------------------
# Self-improving bridge task as a background job
# ---------------------------------------------------------------------------

def queue_self_improving_task(
    persona: str,
    task: str,
    wait_s: float | None = None,
    max_attempts: int = 2,
    use_local_model: bool = True,
    bypass_sentinel: bool = False,
) -> dict[str, Any]:
    """
    Queue a background job that runs the BES-inspired self-improve loop,
    using the text bridge as the big-model channel.

    Pip's small local model (if present) decomposes the task into checkable
    subgoals; she frames the request, sends it to the tool, scores the reply
    against the subgoals, and retries with a recombined framing if needed.
    Every run sharpens the strategy memory.
    """
    if not bypass_sentinel and not pip_sentinel.autonomy_allowed():
        st = pip_sentinel.status()
        return {
            "ok": False,
            "blocked": True,
            "reason": "sentinel_posture",
            "posture": st["posture"],
            "message": f"Self-improving work paused — security posture is {st['posture']}.",
        }

    def run(job_id: str) -> str:
        from . import pip_self_improve

        model_fn = None
        if use_local_model:
            try:
                model_fn = pip_self_improve.ollama_model_fn()
                # cheap reachability probe
                model_fn("ping")
            except Exception:
                model_fn = None
                pip_jobs.append_log(job_id, "No local model; using heuristic decomposition.")

        def send_fn(text: str) -> str:
            with _BRIDGE_LOCK:
                pip_jobs.append_log(job_id, f"Bridge → {persona} (improve attempt)")
                res = pip_text_bridge.send(persona, text, response_wait_s=wait_s)
                if res.needs_manual_copy:
                    pip_jobs.append_log(job_id, "Response needs manual copy; scoring what we have.")
                return res.response

        result = pip_self_improve.improve_loop(
            task, send_fn=send_fn, model_fn=model_fn, max_attempts=max_attempts,
        )

        entry = {
            "job_id": job_id,
            "kind": "self_improving_task",
            "persona": persona,
            "task": task,
            "task_type": result.task_type,
            "ok": result.ok,
            "score": result.score,
            "attempts": result.attempts,
            "framing_used": result.framing_used,
            "response": result.response,
            "response_length": len(result.response),
            "subgoals": result.subgoals,
            "error": result.error,
            "finished_at": utc_now(),
        }
        _write_result(entry)
        pip_jobs.append_log(
            job_id,
            f"Self-improve done: score={result.score:.2f} over {result.attempts} attempt(s).",
        )
        return f"score={result.score:.2f} attempts={result.attempts}"

    return pip_jobs.start_job(
        "self_improving_task",
        f"improve[{persona}]: {task[:60]}",
        run,
        details={"persona": persona, "task": task, "max_attempts": max_attempts},
    )


def status() -> dict[str, Any]:
    from . import pip_self_improve
    sentinel = pip_sentinel.status()
    return {
        "bridge_autonomy_allowed": sentinel["autonomy_allowed"],
        "sentinel_posture": sentinel["posture"],
        "recent_results": list_results()[-5:],
        "strategy_memory": pip_self_improve.status(),
    }
