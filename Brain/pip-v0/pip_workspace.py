#!/usr/bin/env python3
from __future__ import annotations

import fnmatch
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pip_platform


ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST = ROOT / "approved_workspaces.json"


@dataclass(frozen=True)
class Workspace:
    key: str
    name: str
    root: Path
    readable_paths: list[str]
    writable_draft_path: str
    denied_globs: list[str]
    text_extensions: set[str]
    max_file_bytes: int

    @property
    def draft_dir(self) -> Path:
        return self.root / self.writable_draft_path


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def timestamp_slug(value: str) -> str:
    return value.replace("+00:00", "Z").replace(":", "").replace("-", "").replace("T", "_")


def load_manifest(manifest_path: str | Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    path = Path(manifest_path)
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_workspace_root(raw_root: str) -> Path:
    expanded = raw_root.replace("${BRAIN_ROOT}", str(pip_platform.BRAIN_ROOT))
    path = Path(expanded).expanduser()
    if not path.is_absolute():
        path = pip_platform.BRAIN_ROOT / path
    return path.resolve()


def load_workspace(workspace_key: str | None = None, manifest_path: str | Path = DEFAULT_MANIFEST) -> Workspace:
    manifest = load_manifest(manifest_path)
    key = workspace_key or manifest.get("default_workspace")
    raw = manifest.get("workspaces", {}).get(key)
    if not raw:
        raise ValueError(f"Unknown workspace: {key}")

    root = resolve_workspace_root(raw["root"])
    if not root.exists():
        raise FileNotFoundError(f"Workspace root does not exist: {root}")

    return Workspace(
        key=key,
        name=raw.get("name", key),
        root=root,
        readable_paths=list(raw.get("readable_paths", [])),
        writable_draft_path=raw["writable_draft_path"],
        denied_globs=list(raw.get("denied_globs", [])),
        text_extensions={item.lower() for item in raw.get("text_extensions", [])},
        max_file_bytes=int(raw.get("max_file_bytes", 500000)),
    )


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def read_json_default(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(default)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raw = dict(default)
        raw["warning"] = f"{path.name} could not be parsed and was reset"
    return raw if isinstance(raw, dict) else dict(default)


def relpath(workspace: Workspace, path: Path) -> str:
    return path.resolve().relative_to(workspace.root).as_posix()


def is_inside(parent: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def is_denied(workspace: Workspace, relative_path: str) -> bool:
    normalized = relative_path.replace("\\", "/")
    for pattern in workspace.denied_globs:
        pattern = pattern.replace("\\", "/")
        if fnmatch.fnmatch(normalized, pattern) or fnmatch.fnmatch(Path(normalized).name, pattern):
            return True
    return False


def ensure_draft_dir(workspace: Workspace) -> Path:
    draft_dir = workspace.draft_dir.resolve()
    if not is_inside(workspace.root, draft_dir):
        raise ValueError(f"Draft path escapes workspace root: {draft_dir}")
    draft_dir.mkdir(parents=True, exist_ok=True)
    return draft_dir


def iter_allowed_files(workspace: Workspace) -> list[Path]:
    files: list[Path] = []
    for item in workspace.readable_paths:
        candidate = (workspace.root / item).resolve()
        if not is_inside(workspace.root, candidate):
            continue
        if candidate.is_file():
            possible_files = [candidate]
        elif candidate.is_dir():
            possible_files = [path for path in candidate.rglob("*") if path.is_file()]
        else:
            continue

        for path in possible_files:
            relative = relpath(workspace, path)
            if is_denied(workspace, relative):
                continue
            if path.suffix.lower() not in workspace.text_extensions:
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size > workspace.max_file_bytes:
                continue
            files.append(path)
    return sorted(set(files), key=lambda path: relpath(workspace, path).lower())


def read_text_sample(path: Path, limit: int = 6000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def classify_file(relative_path: str) -> str:
    lower = relative_path.lower()
    if lower.endswith("readme.md") or "handoff" in lower or "notes" in lower:
        return "project_notes"
    if lower.startswith("levels/"):
        return "level_config"
    if lower.endswith(".py") or lower.endswith(".ps1"):
        return "builder_code"
    if lower.endswith(".json"):
        return "project_data"
    return "reference"


def scan_workspace(workspace_key: str | None = None, manifest_path: str | Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    workspace = load_workspace(workspace_key, manifest_path)
    draft_dir = ensure_draft_dir(workspace)
    files = iter_allowed_files(workspace)
    inventory: list[dict[str, Any]] = []
    samples: dict[str, str] = {}

    for path in files:
        relative = relpath(workspace, path)
        stat = path.stat()
        inventory.append(
            {
                "path": relative,
                "bytes": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).replace(microsecond=0).isoformat(),
                "kind": classify_file(relative),
            }
        )
        if relative in {"README.md", "levels/quiet_web.json"} or relative.startswith("docs/"):
            samples[relative] = read_text_sample(path)

    payload = {
        "workspace": workspace.key,
        "workspace_name": workspace.name,
        "root": str(workspace.root),
        "draft_dir": str(draft_dir),
        "generated_at": utc_now(),
        "mode": "draft_only",
        "permissions": {
            "can_read": workspace.readable_paths,
            "can_write_only": workspace.writable_draft_path,
            "denied_globs": workspace.denied_globs,
        },
        "file_count": len(inventory),
        "inventory": inventory,
        "samples": samples,
    }
    write_json(draft_dir / "workspace_scan.json", payload)
    return payload


def _find_sample(scan: dict[str, Any], suffix: str) -> str:
    for path, text in scan.get("samples", {}).items():
        if path.endswith(suffix):
            return text
    return ""


def _contains(text: str, needle: str) -> bool:
    return needle.lower() in text.lower()


def build_digest_markdown(scan: dict[str, Any]) -> str:
    readme = _find_sample(scan, "README.md")
    blueprint_present = any("prototype" in item["path"].lower() or "handoff" in item["path"].lower() for item in scan["inventory"])
    has_builder = any(item["kind"] == "builder_code" for item in scan["inventory"])
    has_level_config = any(item["kind"] == "level_config" for item in scan["inventory"])
    current_loop = "calm spelling prototype"
    if _contains(readme, "spelling prototype"):
        current_loop = "calm spelling prototype with letters, target words, trails, and soft feedback"

    lines = [
        "# Garden Spiders Pip Digest",
        "",
        f"Generated: {scan['generated_at']}",
        "",
        "## Current Read",
        f"- Workspace: {scan['workspace_name']}",
        f"- Current playable shape: {current_loop}.",
        f"- Project has builder scripts: {'yes' if has_builder else 'no'}.",
        f"- Project has level configs: {'yes' if has_level_config else 'no'}.",
        f"- Prototype/handoff notes detected: {'yes' if blueprint_present else 'no'}.",
        "",
        "## Core Direction",
        "- Keep the existing Quiet Web prototype stable while Pip drafts the bridge toward the Garden Survival v0.1 idea.",
        "- The target identity is stillness, web placement, decay, coherence, human perception, and a protection moment.",
        "- Pip should not rewrite project JSON directly yet; it should draft small, reviewable steps first.",
        "",
        "## Useful Files",
    ]
    for item in scan["inventory"][:20]:
        lines.append(f"- `{item['path']}` ({item['kind']}, {item['bytes']} bytes)")
    if len(scan["inventory"]) > 20:
        lines.append(f"- ...and {len(scan['inventory']) - 20} more approved files.")

    lines.extend(
        [
            "",
            "## Next Compression",
            "- The next best move is not a big autonomous build. It is a bridge spec that translates the existing spelling prototype into the web/coherence/protector loop.",
            "- After that bridge is approved, Pip can draft one narrow implementation patch at a time.",
        ]
    )
    return "\n".join(lines) + "\n"


def condense_workspace(workspace_key: str | None = None, manifest_path: str | Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    scan = scan_workspace(workspace_key, manifest_path)
    workspace = load_workspace(workspace_key, manifest_path)
    draft_dir = ensure_draft_dir(workspace)
    digest = build_digest_markdown(scan)
    digest_path = draft_dir / "project_digest.md"
    write_text(digest_path, digest)

    memory_update = load_workspace_memory(workspace)
    memory_update["workspace"] = workspace.key
    memory_update["workspace_name"] = workspace.name
    memory_update["last_digest_at"] = scan["generated_at"]
    memory_update["last_digest"] = relpath(workspace, digest_path)
    memory_update["mode"] = "draft_only"
    memory_update["approved_write_scope"] = workspace.writable_draft_path
    write_json(draft_dir / "memory_update.json", memory_update)

    return {
        "workspace": workspace.key,
        "digest": str(digest_path),
        "memory_update": str(draft_dir / "memory_update.json"),
        "file_count": scan["file_count"],
    }


def next_tasks_payload(workspace: Workspace) -> dict[str, Any]:
    return {
        "workspace": workspace.key,
        "generated_at": utc_now(),
        "mode": "draft_only",
        "tasks": [
            {
                "rank": 1,
                "title": "Draft the Quiet Web to Survival v0.1 bridge spec",
                "why": "The current project is a stable spelling prototype, while the concept target is web placement, decay, coherence, destroyer/protector behavior, and protection.",
                "acceptance": [
                    "Names the minimum objects and variables for the survival loop.",
                    "Keeps the existing Quiet Web prototype untouched.",
                    "Identifies one safe implementation slice for review.",
                ],
                "review_files": ["README.md", "docs/garden_spiders_template_handoff.md", "levels/quiet_web.json"],
            },
            {
                "rank": 2,
                "title": "Draft a no-code tuning sheet for web/coherence feel",
                "why": "The emotional core depends on timing and pressure before complex AI is added.",
                "acceptance": [
                    "Defines starter values for coherence drain, stillness recovery, web decay, and cooldown.",
                    "Flags which values should be exposed in level config.",
                    "Includes fail and soft-win tuning notes.",
                ],
                "review_files": ["levels/quiet_web.json"],
            },
            {
                "rank": 3,
                "title": "Draft protector/destroyer event acceptance tests",
                "why": "Human perception is the riskiest new mechanic and should be testable before it is built.",
                "acceptance": [
                    "Defines observable pass/fail checks for destroyer web removal.",
                    "Defines observable pass/fail checks for protector intervention.",
                    "Keeps the first test plan compatible with the current validator style.",
                ],
                "review_files": ["validate_quiet_web.py", "garden_spiders_builder/"],
            },
        ],
    }


def classify_action_permission(action_type: str) -> dict[str, Any]:
    normalized = action_type.strip().lower().replace("-", "_").replace(" ", "_")
    auto_allowed = {
        "read_workspace",
        "scan_workspace",
        "condense_workspace",
        "draft_workspace_artifact",
        "write_draft",
        "update_memory",
        "export_status",
        "schedule_next_wake",
    }
    requires_permission = {
        "modify_original",
        "modify_project_file",
        "code_edit",
        "run_build",
        "install_package",
        "open_network_service",
        "send_message",
        "phone_app_automation",
        "zerotap_action",
        "delete_file",
        "push_remote",
        "autonomous_goal",
        "arbitrary_python",
        "ui_automation",
        "keyboard_recording",
        "system_optimization",
    }
    if normalized in auto_allowed:
        return {
            "action_type": normalized,
            "tier": "auto_allowed",
            "reason": "Local, reversible, and restricted to approved workspace/draft state.",
        }
    if normalized in requires_permission:
        return {
            "action_type": normalized,
            "tier": "requires_permission",
            "reason": "This can affect originals, external systems, apps, people, packages, or shared state.",
        }
    return {
        "action_type": normalized or "unknown",
        "tier": "requires_permission",
        "reason": "Unknown actions require approval until Pip has an explicit safety rule for them.",
    }


def permission_queue_path(workspace: Workspace) -> Path:
    return workspace.draft_dir / "permission_queue.json"


def ambient_state_path(workspace: Workspace) -> Path:
    return workspace.draft_dir / "ambient_state.json"


def load_permission_queue(workspace: Workspace) -> dict[str, Any]:
    return read_json_default(
        permission_queue_path(workspace),
        {
            "workspace": workspace.key,
            "workspace_name": workspace.name,
            "pending": [],
            "history": [],
        },
    )


def save_permission_queue(workspace: Workspace, queue: dict[str, Any]) -> None:
    queue["workspace"] = workspace.key
    queue["workspace_name"] = workspace.name
    queue["pending"] = queue.get("pending", [])
    queue["history"] = queue.get("history", [])[-50:]
    write_json(permission_queue_path(workspace), queue)


def request_permission(
    workspace_key: str | None,
    action_type: str,
    title: str,
    rationale: str,
    manifest_path: str | Path = DEFAULT_MANIFEST,
) -> dict[str, Any]:
    workspace = load_workspace(workspace_key, manifest_path)
    ensure_draft_dir(workspace)
    classification = classify_action_permission(action_type)
    now = utc_now()
    request_id_seed = f"{workspace.key}:{action_type}:{title}:{now}"
    request_id = hashlib.sha1(request_id_seed.encode("utf-8")).hexdigest()[:12]
    request = {
        "id": request_id,
        "workspace": workspace.key,
        "action_type": classification["action_type"],
        "tier": classification["tier"],
        "title": title,
        "rationale": rationale,
        "status": "pending" if classification["tier"] == "requires_permission" else "auto_allowed",
        "created_at": now,
        "resolved_at": None,
        "decision_note": "",
        "classification_reason": classification["reason"],
    }
    queue = load_permission_queue(workspace)
    if classification["tier"] == "requires_permission":
        queue.setdefault("pending", []).append(request)
    else:
        queue.setdefault("history", []).append(request)
    save_permission_queue(workspace, queue)
    return request


def resolve_permission(
    workspace_key: str | None,
    request_id: str,
    decision: str,
    note: str = "",
    manifest_path: str | Path = DEFAULT_MANIFEST,
) -> dict[str, Any]:
    if decision not in {"approved", "denied"}:
        raise ValueError("decision must be approved or denied")
    workspace = load_workspace(workspace_key, manifest_path)
    ensure_draft_dir(workspace)
    queue = load_permission_queue(workspace)
    pending = queue.get("pending", [])
    match = None
    remaining = []
    for item in pending:
        if item.get("id") == request_id:
            match = item
        else:
            remaining.append(item)
    if not match:
        raise ValueError(f"Unknown pending permission request: {request_id}")
    match["status"] = decision
    match["resolved_at"] = utc_now()
    match["decision_note"] = note
    queue["pending"] = remaining
    queue.setdefault("history", []).append(match)
    save_permission_queue(workspace, queue)
    return match


def load_ambient_state(workspace: Workspace) -> dict[str, Any]:
    state = read_json_default(
        ambient_state_path(workspace),
        {
            "workspace": workspace.key,
            "workspace_name": workspace.name,
            "status": "idle",
            "cycle_count": 0,
            "last_cycle": None,
            "next_wake_at": None,
            "next_context": "",
            "transcripts": [],
        },
    )
    state["workspace"] = workspace.key
    state["workspace_name"] = workspace.name
    state.setdefault("transcripts", [])
    return state


def save_ambient_state(workspace: Workspace, state: dict[str, Any]) -> None:
    state["workspace"] = workspace.key
    state["workspace_name"] = workspace.name
    state["transcripts"] = state.get("transcripts", [])[-20:]
    write_json(ambient_state_path(workspace), state)


def queue_next_wake(
    workspace_key: str | None = None,
    wake_minutes: int = 30,
    context: str = "Run the next supervised draft-only ambient cycle.",
    manifest_path: str | Path = DEFAULT_MANIFEST,
) -> dict[str, Any]:
    workspace = load_workspace(workspace_key, manifest_path)
    ensure_draft_dir(workspace)
    wake_minutes = max(1, min(int(wake_minutes), 1440))
    now_dt = parse_utc(utc_now())
    next_wake = (now_dt + timedelta(minutes=wake_minutes)).replace(microsecond=0).isoformat()
    state = load_ambient_state(workspace)
    state["status"] = "scheduled"
    state["next_wake_at"] = next_wake
    state["next_context"] = context
    state["updated_at"] = utc_now()
    save_ambient_state(workspace, state)
    return state


def run_ambient_cycle(
    workspace_key: str | None = None,
    wake_minutes: int = 30,
    context: str = "Review latest draft proposal and continue Garden Spiders planning.",
    manifest_path: str | Path = DEFAULT_MANIFEST,
) -> dict[str, Any]:
    workspace = load_workspace(workspace_key, manifest_path)
    draft_dir = ensure_draft_dir(workspace)
    started_at = utc_now()
    state = load_ambient_state(workspace)
    state["status"] = "running"
    state["current_cycle_started_at"] = started_at
    save_ambient_state(workspace, state)

    operations: list[dict[str, Any]] = []
    for action_type, title in [
        ("scan_workspace", "Scan approved Garden Spiders files"),
        ("condense_workspace", "Condense project state into a digest"),
        ("draft_workspace_artifact", "Draft next supervised actions"),
        ("schedule_next_wake", "Schedule the next ambient check"),
    ]:
        operations.append(
            {
                "action_type": action_type,
                "title": title,
                "classification": classify_action_permission(action_type),
            }
        )

    draft_result = draft_next_actions(workspace.key, manifest_path)
    queue = load_permission_queue(workspace)
    proposal = read_json_if_exists(draft_dir / "proposal_card.json") or {}
    memory = load_workspace_memory(workspace)
    latest_feedback = memory.get("last_feedback") or {}
    if latest_feedback.get("status") == "accepted":
        already_pending = any(
            item.get("action_type") == "code_edit"
            and item.get("status") == "pending"
            and "Quiet Web to Survival" in item.get("title", "")
            for item in queue.get("pending", [])
        )
        if not already_pending:
            request = request_permission(
                workspace.key,
                "code_edit",
                "Implement the first approved Quiet Web to Survival v0.1 code slice",
                "The latest proposal was accepted. Any original project-file edit must wait for explicit approval.",
                manifest_path,
            )
            operations.append(
                {
                    "action_type": "code_edit",
                    "title": request["title"],
                    "classification": classify_action_permission("code_edit"),
                    "permission_request": request,
                }
            )
            queue = load_permission_queue(workspace)

    scheduled_state = queue_next_wake(workspace.key, wake_minutes, context, manifest_path)
    completed_at = utc_now()
    transcript = {
        "workspace": workspace.key,
        "started_at": started_at,
        "completed_at": completed_at,
        "summary": "Ran Garden Spiders ambient cycle: scanned approved files, refreshed digest, drafted next actions, and updated status.",
        "mode": "draft_only",
        "operations": operations,
        "draft_outputs": {
            "project_digest": str(draft_dir / "project_digest.md"),
            "next_3_tasks": str(draft_dir / "next_3_tasks.json"),
            "proposal_card": str(draft_dir / "proposal_card.json"),
            "control_status": str(draft_dir / "control_status.json"),
        },
        "latest_proposal": proposal,
        "pending_permissions": queue.get("pending", []),
        "next_wake_at": scheduled_state.get("next_wake_at"),
        "next_context": scheduled_state.get("next_context"),
        "draft_result": {
            "file_count": draft_result.get("condensation", {}).get("file_count"),
            "proposal_card": draft_result.get("proposal_card"),
        },
    }
    transcript_path = draft_dir / f"ambient_transcript_{timestamp_slug(started_at)}.json"
    write_json(transcript_path, transcript)

    state = load_ambient_state(workspace)
    state["status"] = "scheduled"
    state["cycle_count"] = int(state.get("cycle_count", 0)) + 1
    state["last_cycle"] = {
        "started_at": started_at,
        "completed_at": completed_at,
        "summary": transcript["summary"],
        "transcript": relpath(workspace, transcript_path),
        "pending_permission_count": len(queue.get("pending", [])),
    }
    state.setdefault("transcripts", []).append(relpath(workspace, transcript_path))
    state["next_wake_at"] = scheduled_state.get("next_wake_at")
    state["next_context"] = scheduled_state.get("next_context")
    state["updated_at"] = completed_at
    save_ambient_state(workspace, state)
    export_control_status(workspace.key, manifest_path)
    return {
        "workspace": workspace.key,
        "ambient_state": state,
        "transcript": str(transcript_path),
        "pending_permissions": queue.get("pending", []),
    }


def draft_next_actions(workspace_key: str | None = None, manifest_path: str | Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    condensation = condense_workspace(workspace_key, manifest_path)
    workspace = load_workspace(workspace_key, manifest_path)
    draft_dir = ensure_draft_dir(workspace)
    tasks = next_tasks_payload(workspace)
    proposal = {
        "workspace": workspace.key,
        "generated_at": tasks["generated_at"],
        "status": "proposed",
        "proposal": "Approve Pip to draft the Quiet Web to Survival v0.1 bridge spec.",
        "evidence": "Garden Spiders has a working Quiet Web project plus a blueprint pointing toward webs, decay, coherence, destroyer/protector pressure, and a protection moment.",
        "rationale_tags": ["garden_spiders", "draft_only", "bridge_spec", "phone_control_ready"],
        "next_task": tasks["tasks"][0],
        "writes_allowed_only_under": str(draft_dir),
    }
    write_json(draft_dir / "next_3_tasks.json", tasks)
    write_json(draft_dir / "proposal_card.json", proposal)

    memory = load_workspace_memory(workspace)
    memory["latest_proposal"] = proposal
    memory["last_tasks_at"] = tasks["generated_at"]
    memory.setdefault("feedback_history", [])
    write_json(draft_dir / "memory_update.json", memory)

    status = export_control_status(workspace.key, manifest_path)
    return {
        "workspace": workspace.key,
        "condensation": condensation,
        "next_3_tasks": str(draft_dir / "next_3_tasks.json"),
        "proposal_card": str(draft_dir / "proposal_card.json"),
        "memory_update": str(draft_dir / "memory_update.json"),
        "status": status,
    }


def load_workspace_memory(workspace: Workspace) -> dict[str, Any]:
    path = workspace.draft_dir / "memory_update.json"
    if not path.exists():
        return {
            "workspace": workspace.key,
            "workspace_name": workspace.name,
            "mode": "draft_only",
            "feedback_history": [],
        }
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "workspace": workspace.key,
            "workspace_name": workspace.name,
            "mode": "draft_only",
            "feedback_history": [],
            "warning": "memory_update.json could not be parsed and was reset",
        }


def read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"error": f"Could not parse {path.name}"}


def record_feedback(
    workspace_key: str | None,
    status: str,
    note: str = "",
    manifest_path: str | Path = DEFAULT_MANIFEST,
) -> dict[str, Any]:
    if status not in {"accepted", "rejected", "deferred"}:
        raise ValueError("status must be accepted, rejected, or deferred")
    workspace = load_workspace(workspace_key, manifest_path)
    draft_dir = ensure_draft_dir(workspace)
    memory = load_workspace_memory(workspace)
    entry = {
        "status": status,
        "note": note,
        "recorded_at": utc_now(),
        "proposal": read_json_if_exists(draft_dir / "proposal_card.json"),
    }
    memory.setdefault("feedback_history", []).append(entry)
    memory["last_feedback"] = entry
    if memory.get("latest_proposal"):
        memory["latest_proposal"]["status"] = status
    proposal_path = draft_dir / "proposal_card.json"
    proposal = read_json_if_exists(proposal_path)
    if proposal:
        proposal["status"] = status
        write_json(proposal_path, proposal)
    write_json(draft_dir / "memory_update.json", memory)
    return entry


def export_control_status(workspace_key: str | None = None, manifest_path: str | Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    workspace = load_workspace(workspace_key, manifest_path)
    draft_dir = ensure_draft_dir(workspace)
    latest_proposal = read_json_if_exists(draft_dir / "proposal_card.json")
    latest_memory = read_json_if_exists(draft_dir / "memory_update.json")
    latest_scan = read_json_if_exists(draft_dir / "workspace_scan.json")
    ambient_state = load_ambient_state(workspace)
    permission_queue = load_permission_queue(workspace)
    if latest_memory and latest_memory.get("latest_proposal"):
        memory_proposal = latest_memory["latest_proposal"]
        if latest_proposal:
            latest_proposal["status"] = memory_proposal.get("status", latest_proposal.get("status"))
        else:
            latest_proposal = memory_proposal
    status = {
        "workspace": workspace.key,
        "workspace_name": workspace.name,
        "root": str(workspace.root),
        "draft_dir": str(draft_dir),
        "mode": "draft_only",
        "generated_at": utc_now(),
        "latest_proposal": latest_proposal,
        "latest_memory": latest_memory,
        "latest_scan_summary": {
            "generated_at": latest_scan.get("generated_at") if latest_scan else None,
            "file_count": latest_scan.get("file_count") if latest_scan else 0,
        },
        "ambient": ambient_state,
        "permissions": {
            "pending": permission_queue.get("pending", []),
            "recent_history": permission_queue.get("history", [])[-10:],
        },
        "available_actions": [
            "run_scan",
            "run_ambient",
            "schedule_next_wake",
            "approve",
            "reject",
            "defer",
            "inspect_memory",
            "resolve_permission",
        ],
    }
    write_json(draft_dir / "control_status.json", status)
    return status
