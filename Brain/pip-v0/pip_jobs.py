#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pip_config


_LOCK = threading.Lock()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def jobs_dir() -> Path:
    path = pip_config.get_memory_path() / "jobs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def jobs_path() -> Path:
    return jobs_dir() / "jobs.json"


def _read_jobs() -> dict[str, Any]:
    path = jobs_path()
    if not path.exists():
        return {"jobs": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"jobs": []}


def _write_jobs(data: dict[str, Any]) -> None:
    data["jobs"] = data.get("jobs", [])[-50:]
    jobs_path().write_text(json.dumps(data, indent=2), encoding="utf-8")


def _job_id(kind: str, title: str) -> str:
    seed = f"{kind}:{title}:{utc_now()}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


def _update_job(job_id: str, **updates: Any) -> dict[str, Any] | None:
    with _LOCK:
        data = _read_jobs()
        match = None
        for job in data.get("jobs", []):
            if job.get("id") == job_id:
                job.update(updates)
                match = job
                break
        _write_jobs(data)
        return match


def log_path(job_id: str) -> Path:
    return jobs_dir() / f"{job_id}.log"


def stop_path(job_id: str) -> Path:
    return jobs_dir() / f"{job_id}.stop"


def append_log(job_id: str, message: str) -> None:
    line = f"[{utc_now()}] {message.rstrip()}\n"
    with _LOCK:
        with open(log_path(job_id), "a", encoding="utf-8") as handle:
            handle.write(line)


def should_stop(job_id: str) -> bool:
    return stop_path(job_id).exists()


def list_jobs() -> dict[str, Any]:
    data = _read_jobs()
    for job in data.get("jobs", []):
        path = log_path(job["id"])
        if path.exists():
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
                job["latest_log"] = lines[-8:]
            except Exception:
                job["latest_log"] = []
        else:
            job["latest_log"] = []
    return data


def request_stop(job_id: str) -> dict[str, Any]:
    if not job_id:
        return {"ok": False, "job": None, "message": "Missing job id."}

    data = _read_jobs()
    if not any(job.get("id") == job_id for job in data.get("jobs", [])):
        return {"ok": False, "job": None, "message": "Unknown job."}

    stop_path(job_id).write_text(utc_now(), encoding="utf-8")
    job = _update_job(job_id, status="stop_requested", stop_requested_at=utc_now())
    append_log(job_id, "Stop requested by user.")
    return {"ok": bool(job), "job": job, "message": "Stop requested." if job else "Unknown job."}


def start_job(kind: str, title: str, target: Callable[[str], Any], details: dict[str, Any] | None = None) -> dict[str, Any]:
    job_id = _job_id(kind, title)
    job = {
        "id": job_id,
        "kind": kind,
        "title": title,
        "status": "running",
        "created_at": utc_now(),
        "started_at": utc_now(),
        "finished_at": None,
        "stop_requested_at": None,
        "details": details or {},
        "log_path": str(log_path(job_id)),
    }
    with _LOCK:
        data = _read_jobs()
        data.setdefault("jobs", []).append(job)
        _write_jobs(data)
    append_log(job_id, f"Started {kind}: {title}")

    def runner() -> None:
        try:
            result = target(job_id)
            if should_stop(job_id):
                _update_job(job_id, status="stopped", finished_at=utc_now(), result=str(result))
                append_log(job_id, "Stopped.")
            else:
                _update_job(job_id, status="completed", finished_at=utc_now(), result=str(result))
                append_log(job_id, f"Completed: {result}")
        except Exception as exc:
            _update_job(job_id, status="failed", finished_at=utc_now(), error=str(exc))
            append_log(job_id, f"Failed: {exc}")

    thread = threading.Thread(target=runner, daemon=True, name=f"pip-job-{job_id}")
    thread.start()
    return job


def start_autonomous_goal(goal_text: str) -> dict[str, Any]:
    def run(job_id: str) -> Any:
        import pip_goal_engine
        import pip_token_guard

        assessment = pip_token_guard.assess_interaction(
            goal_text,
            intent="job",
            source_type="first_hand",
            source_name="Approved Pip job",
        )
        append_log(job_id, f"Token Governor: {assessment['mode']} / {assessment['priority']} / {assessment['estimated_tokens']} est.")
        if not assessment["allowed"]:
            pip_token_guard.record_event(
                "job",
                estimated_tokens=assessment["estimated_tokens"],
                actual_tokens=0,
                saved_tokens=assessment["estimated_tokens"],
                note=f"Blocked inside job runner: {assessment['reason']}",
            )
            return assessment["nudge"]
        engine = pip_goal_engine.PipGoalEngine(max_steps=10)
        result = engine.run_goal(
            goal_text,
            yield_logs=False,
            log_fn=lambda message: append_log(job_id, message),
            should_stop=lambda: should_stop(job_id),
        )
        pip_token_guard.record_event("job", estimated_tokens=assessment["estimated_tokens"])
        return result

    return start_job(
        "autonomous_goal",
        goal_text[:90] or "Autonomous Pip goal",
        run,
        details={"goal": goal_text},
    )
