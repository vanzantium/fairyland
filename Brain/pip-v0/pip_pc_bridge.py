#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from pip_engine import PipEngine
from pip_phone_bridge import read_json_if_exists, utc_now, validate_usage_events, write_json


ROOT = Path(__file__).resolve().parent
IMPORTS_DIR = ROOT / "imports"
DEFAULT_USAGE_PATH = IMPORTS_DIR / "pc_usage_latest.json"
DEFAULT_MEMORY_PATH = IMPORTS_DIR / "pc_memory.json"
DEFAULT_DREAM_PATH = IMPORTS_DIR / "pc_latest_dream.json"
DEFAULT_PROPOSAL_PATH = IMPORTS_DIR / "pc_proposal_card.json"
DEFAULT_STATUS_PATH = IMPORTS_DIR / "pc_bridge_status.json"


def load_usage_json_text(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid PC usage JSON: {exc}") from exc


def run_pc_optimizer(
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
        "source": "pc_usage",
        "status": "proposed",
    }
    write_json(dream_path, result)
    write_json(proposal_path, proposal)
    status = get_pc_status()
    status["proposal"] = proposal
    write_json(status_path, status)
    return status


def import_pc_usage_text(
    text: str,
    source_name: str = "pc_usage_upload.json",
    run_optimizer: bool = True,
) -> dict[str, Any]:
    raw = load_usage_json_text(text)
    validation = validate_usage_events(raw)
    if not validation["ok"]:
        status = {
            "generated_at": utc_now(),
            "mode": "pc_optimizer",
            "validation": validation,
            "imported": False,
            "source_name": source_name,
        }
        write_json(DEFAULT_STATUS_PATH, status)
        return status

    IMPORTS_DIR.mkdir(parents=True, exist_ok=True)
    write_json(DEFAULT_USAGE_PATH, raw)
    archive_path = IMPORTS_DIR / f"pc_upload_{utc_now().replace(':', '').replace('-', '')}.json"
    shutil.copyfile(DEFAULT_USAGE_PATH, archive_path)

    status = get_pc_status()
    status.update(
        {
            "validation": validation,
            "imported": True,
            "source_name": source_name,
            "archive_path": str(archive_path),
        }
    )
    write_json(DEFAULT_STATUS_PATH, status)
    if run_optimizer:
        status = run_pc_optimizer()
        status.update(
            {
                "validation": validation,
                "imported": True,
                "source_name": source_name,
                "archive_path": str(archive_path),
            }
        )
        write_json(DEFAULT_STATUS_PATH, status)
    return status


def get_pc_status() -> dict[str, Any]:
    return {
        "generated_at": utc_now(),
        "mode": "pc_optimizer",
        "latest_usage": str(DEFAULT_USAGE_PATH),
        "latest_dream": str(DEFAULT_DREAM_PATH),
        "latest_proposal": str(DEFAULT_PROPOSAL_PATH),
        "memory": str(DEFAULT_MEMORY_PATH),
        "proposal": read_json_if_exists(DEFAULT_PROPOSAL_PATH),
    }
