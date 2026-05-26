#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from datetime import timedelta
from pathlib import Path
from typing import Any

from pip_engine import PipEngine


ROOT = Path(__file__).resolve().parent
IMPORTS_DIR = ROOT / "imports"
DEFAULT_USAGE_PATH = IMPORTS_DIR / "s25_usage_last_7_days.json"
DEFAULT_MEMORY_PATH = IMPORTS_DIR / "s25_memory.json"
DEFAULT_DREAM_PATH = IMPORTS_DIR / "s25_latest_dream.json"
DEFAULT_PROPOSAL_PATH = IMPORTS_DIR / "s25_proposal_card.json"
DEFAULT_STATUS_PATH = IMPORTS_DIR / "phone_bridge_status.json"

REQUIRED_USAGE_FIELDS = {
    "timestamp": str,
    "app_name": str,
    "event_type": str,
    "battery_delta": int,
    "notifications_received": int,
    "notifications_dismissed_unread": int,
    "session_duration_seconds": int,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_json_if_exists(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"error": f"Could not parse {path.name}"}


def validate_usage_events(raw: Any) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(raw, list):
        errors.append("root JSON value must be an array")
        raw = []

    event_types: set[str] = set()
    battery_values: list[int] = []
    notification_totals: list[int] = []

    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            errors.append(f"event {index}: must be an object")
            continue

        for field_name, expected_type in REQUIRED_USAGE_FIELDS.items():
            if field_name not in item:
                errors.append(f"event {index}: missing {field_name}")
                continue
            if not isinstance(item[field_name], expected_type):
                errors.append(f"event {index}: {field_name} must be {expected_type.__name__}")

        if not item.get("timestamp"):
            errors.append(f"event {index}: timestamp must be non-empty")
        if not item.get("app_name"):
            errors.append(f"event {index}: app_name must be non-empty")

        for numeric_field in [
            "battery_delta",
            "notifications_received",
            "notifications_dismissed_unread",
            "session_duration_seconds",
        ]:
            value = item.get(numeric_field)
            if isinstance(value, int) and value < 0:
                errors.append(f"event {index}: {numeric_field} must be >= 0")

        duration = item.get("session_duration_seconds")
        if isinstance(duration, int) and duration <= 0:
            errors.append(f"event {index}: session_duration_seconds must be > 0")

        received = item.get("notifications_received")
        dismissed = item.get("notifications_dismissed_unread")
        if isinstance(received, int) and isinstance(dismissed, int) and dismissed > received:
            errors.append(
                f"event {index}: notifications_dismissed_unread cannot exceed notifications_received"
            )

        if isinstance(item.get("event_type"), str):
            event_types.add(item["event_type"])
        if isinstance(item.get("battery_delta"), int):
            battery_values.append(item["battery_delta"])
        if isinstance(item.get("notifications_received"), int):
            notification_totals.append(item["notifications_received"])

    if event_types and event_types != {"launch"}:
        warnings.append(f"non-launch event types present: {sorted(event_types)}")
    if battery_values and all(value == 0 for value in battery_values):
        warnings.append("all battery_delta values are zero")
    if notification_totals and all(value == 0 for value in notification_totals):
        warnings.append("all notifications_received values are zero")

    return {
        "ok": not errors,
        "event_count": len(raw),
        "errors": errors,
        "warnings": warnings,
    }


def parse_manual_summary(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("app,") or line.lower().startswith("app_name,"):
            continue

        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 3:
            raise ValueError(
                f"line {line_number}: expected at least app_name, launches, total_minutes"
            )

        app_name = parts[0]
        launches = int(parts[1])
        total_minutes = float(parts[2])
        notifications_received = int(parts[3]) if len(parts) >= 4 and parts[3] else 0
        notifications_dismissed_unread = int(parts[4]) if len(parts) >= 5 and parts[4] else 0
        battery_delta_total = int(parts[5]) if len(parts) >= 6 and parts[5] else max(0, round(total_minutes / 45))

        if not app_name:
            raise ValueError(f"line {line_number}: app_name must be non-empty")
        if launches <= 0:
            raise ValueError(f"line {line_number}: launches must be > 0")
        if total_minutes <= 0:
            raise ValueError(f"line {line_number}: total_minutes must be > 0")
        if notifications_dismissed_unread > notifications_received:
            raise ValueError(
                f"line {line_number}: dismissed notifications cannot exceed received notifications"
            )
        if battery_delta_total < 0:
            raise ValueError(f"line {line_number}: battery_delta_total must be >= 0")

        rows.append(
            {
                "app_name": app_name,
                "launches": launches,
                "total_minutes": total_minutes,
                "notifications_received": notifications_received,
                "notifications_dismissed_unread": notifications_dismissed_unread,
                "battery_delta_total": battery_delta_total,
            }
        )
    if not rows:
        raise ValueError("manual summary had no app rows")
    return rows


def rows_to_usage_events(rows: list[dict[str, Any]], days: int = 7) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    start = now - timedelta(days=max(1, days))
    events: list[dict[str, Any]] = []
    total_launches = sum(row["launches"] for row in rows)
    event_index = 0

    for row in rows:
        launches = row["launches"]
        total_seconds = int(row["total_minutes"] * 60)
        base_duration = max(1, total_seconds // launches)
        remainder = max(0, total_seconds - base_duration * launches)
        notifications_left = row["notifications_received"]
        dismissed_left = row["notifications_dismissed_unread"]
        battery_left = row["battery_delta_total"]

        for launch_index in range(launches):
            remaining_launches = launches - launch_index
            notifications = notifications_left // remaining_launches if remaining_launches else 0
            dismissed = dismissed_left // remaining_launches if remaining_launches else 0
            battery = battery_left // remaining_launches if remaining_launches else 0
            notifications_left -= notifications
            dismissed_left -= dismissed
            battery_left -= battery
            duration = base_duration + (1 if launch_index < remainder else 0)
            if total_launches > 1:
                offset = (event_index / max(1, total_launches - 1)) * max(1, days * 24 * 60 - 1)
            else:
                offset = 0
            timestamp = start + timedelta(minutes=round(offset))
            events.append(
                {
                    "timestamp": timestamp.isoformat(),
                    "app_name": row["app_name"],
                    "event_type": "launch",
                    "battery_delta": battery,
                    "notifications_received": notifications,
                    "notifications_dismissed_unread": dismissed,
                    "session_duration_seconds": duration,
                }
            )
            event_index += 1

    events.sort(key=lambda item: item["timestamp"])
    return events


def import_manual_summary_text(text: str, source_name: str = "manual_summary.csv") -> dict[str, Any]:
    rows = parse_manual_summary(text)
    events = rows_to_usage_events(rows)
    status = import_phone_usage_text(json.dumps(events), source_name, run_optimizer=True)
    status["manual_summary"] = {
        "source_name": source_name,
        "app_count": len(rows),
        "total_launches": sum(row["launches"] for row in rows),
        "rows": rows,
    }
    write_json(DEFAULT_STATUS_PATH, status)
    return status


def load_usage_json_text(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid usage JSON: {exc}") from exc


def run_phone_optimizer(
    input_path: Path = DEFAULT_USAGE_PATH,
    memory_path: Path = DEFAULT_MEMORY_PATH,
    dream_path: Path = DEFAULT_DREAM_PATH,
    proposal_path: Path = DEFAULT_PROPOSAL_PATH,
    status_path: Path = DEFAULT_STATUS_PATH,
    feedback: str | None = None,
) -> dict[str, Any]:
    engine = PipEngine(memory_path=str(memory_path))
    result = engine.run(str(input_path), feedback=feedback)
    proposal = {
        "proposal_card": result.get("proposal_card", {}),
        "thermal_state": result.get("thermal_state", {}),
        "decision_trace": result.get("decision_trace", {}),
        "memory": result.get("memory", {}),
        "generated_at": utc_now(),
        "source": "s25_usage",
        "status": "proposed",
    }
    write_json(dream_path, result)
    write_json(proposal_path, proposal)

    status = {
        "generated_at": utc_now(),
        "mode": "phone_optimizer",
        "latest_usage": str(input_path),
        "latest_dream": str(dream_path),
        "latest_proposal": str(proposal_path),
        "memory": str(memory_path),
        "validation": validate_usage_events(read_json_if_exists(input_path)),
        "proposal": proposal,
    }
    write_json(status_path, status)
    return status


def import_phone_usage_text(
    text: str,
    source_name: str = "phone_upload.json",
    run_optimizer: bool = True,
) -> dict[str, Any]:
    IMPORTS_DIR.mkdir(parents=True, exist_ok=True)
    raw = load_usage_json_text(text)
    validation = validate_usage_events(raw)
    if not validation["ok"]:
        status = {
            "generated_at": utc_now(),
            "mode": "phone_optimizer",
            "imported": False,
            "source_name": source_name,
            "validation": validation,
            "proposal": read_json_if_exists(DEFAULT_PROPOSAL_PATH),
        }
        write_json(DEFAULT_STATUS_PATH, status)
        return status

    write_json(DEFAULT_USAGE_PATH, raw)
    archive_path = IMPORTS_DIR / f"phone_upload_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    write_json(archive_path, raw)

    if run_optimizer:
        status = run_phone_optimizer()
    else:
        status = {
            "generated_at": utc_now(),
            "mode": "phone_optimizer",
            "latest_usage": str(DEFAULT_USAGE_PATH),
            "validation": validation,
            "proposal": read_json_if_exists(DEFAULT_PROPOSAL_PATH),
        }
        write_json(DEFAULT_STATUS_PATH, status)

    status["imported"] = True
    status["source_name"] = source_name
    status["archive_path"] = str(archive_path)
    status["validation"] = validation
    write_json(DEFAULT_STATUS_PATH, status)
    return status


def import_phone_usage_file(input_path: str | Path, run_optimizer: bool = True) -> dict[str, Any]:
    source = Path(input_path)
    text = source.read_text(encoding="utf-8")
    return import_phone_usage_text(text, source.name, run_optimizer=run_optimizer)


def apply_phone_feedback(feedback: str, note: str = "") -> dict[str, Any]:
    if feedback not in {"accepted", "rejected", "deferred", "resolved"}:
        raise ValueError("feedback must be accepted, rejected, deferred, or resolved")
    status = run_phone_optimizer(feedback=feedback)
    status["last_feedback"] = {
        "feedback": feedback,
        "note": note,
        "recorded_at": utc_now(),
    }
    proposal = read_json_if_exists(DEFAULT_PROPOSAL_PATH) or {}
    proposal["status"] = feedback
    proposal["last_feedback_note"] = note
    write_json(DEFAULT_PROPOSAL_PATH, proposal)
    status["proposal"] = proposal
    write_json(DEFAULT_STATUS_PATH, status)
    return status


def get_phone_status() -> dict[str, Any]:
    status = read_json_if_exists(DEFAULT_STATUS_PATH)
    if isinstance(status, dict):
        return status
    proposal = read_json_if_exists(DEFAULT_PROPOSAL_PATH)
    validation = None
    if DEFAULT_USAGE_PATH.exists():
        validation = validate_usage_events(read_json_if_exists(DEFAULT_USAGE_PATH))
    return {
        "generated_at": utc_now(),
        "mode": "phone_optimizer",
        "latest_usage": str(DEFAULT_USAGE_PATH) if DEFAULT_USAGE_PATH.exists() else None,
        "validation": validation,
        "proposal": proposal,
    }


def reset_phone_bridge_outputs() -> None:
    for path in [DEFAULT_STATUS_PATH, DEFAULT_DREAM_PATH, DEFAULT_PROPOSAL_PATH]:
        if path.exists():
            path.unlink()
    if DEFAULT_MEMORY_PATH.exists():
        backup_path = DEFAULT_MEMORY_PATH.with_suffix(".backup.json")
        shutil.copyfile(DEFAULT_MEMORY_PATH, backup_path)
