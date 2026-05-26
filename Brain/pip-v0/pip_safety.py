#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from pip_workspace import (
    DEFAULT_MANIFEST,
    load_permission_queue,
    load_workspace,
    request_permission,
    save_permission_queue,
    utc_now,
)


DANGEROUS_SKILL_ACTIONS = {
    "run_python_script": "arbitrary_python",
    "hands_type_text": "ui_automation",
    "hands_press_key": "ui_automation",
    "hands_click_mouse": "ui_automation",
    "record_new_macro": "keyboard_recording",
    "trigger_pc_focus_mode": "ui_automation",
}


def request_safety_permission(
    action_type: str,
    title: str,
    rationale: str,
    workspace_key: str | None = None,
    manifest_path: str | Path = DEFAULT_MANIFEST,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request = request_permission(workspace_key, action_type, title, rationale, manifest_path)
    if details:
        workspace = load_workspace(workspace_key, manifest_path)
        queue = load_permission_queue(workspace)
        for bucket in ("pending", "history"):
            for item in queue.get(bucket, []):
                if item.get("id") == request["id"]:
                    item["details"] = details
                    save_permission_queue(workspace, queue)
                    request["details"] = details
                    return request
    return request


def consume_approved_permission(
    action_type: str,
    request_id: str,
    workspace_key: str | None = None,
    manifest_path: str | Path = DEFAULT_MANIFEST,
) -> dict[str, Any]:
    workspace = load_workspace(workspace_key, manifest_path)
    queue = load_permission_queue(workspace)
    normalized = action_type.strip().lower().replace("-", "_").replace(" ", "_")

    for item in queue.get("history", []):
        if item.get("id") != request_id:
            continue
        if item.get("action_type") != normalized:
            return {
                "ok": False,
                "message": f"Approved request {request_id} is for {item.get('action_type')}, not {normalized}.",
            }
        if item.get("status") != "approved":
            return {"ok": False, "message": f"Request {request_id} was not approved."}
        if item.get("consumed_at"):
            return {"ok": False, "message": f"Request {request_id} was already used."}

        item["consumed_at"] = utc_now()
        save_permission_queue(workspace, queue)
        return {"ok": True, "request": item}

    return {"ok": False, "message": f"No approved permission found for request {request_id}."}


def gate_skill(skill_name: str, args: argparse.Namespace, summary: str) -> dict[str, Any] | None:
    action_type = DANGEROUS_SKILL_ACTIONS.get(skill_name)
    if not action_type:
        return None

    workspace = getattr(args, "workspace", None)
    manifest = getattr(args, "manifest", DEFAULT_MANIFEST)
    approved_request_id = getattr(args, "approved_request_id", None)

    if approved_request_id:
        result = consume_approved_permission(action_type, approved_request_id, workspace, manifest)
        if result["ok"]:
            return None
        return {
            "skill": skill_name,
            "ok": False,
            "blocked": True,
            "message": result["message"],
        }

    request = request_safety_permission(
        action_type,
        title=f"Approve Pip skill: {skill_name}",
        rationale=summary,
        workspace_key=workspace,
        manifest_path=manifest,
        details={"skill": skill_name},
    )
    return {
        "skill": skill_name,
        "ok": False,
        "blocked": True,
        "message": "Safety approval required before Pip can run this skill.",
        "permission_request": request,
    }
