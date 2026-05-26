#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from pip_engine import PipEngine
from pip_phone_bridge import (
    apply_phone_feedback as apply_phone_feedback_impl,
    get_phone_status as get_phone_status_impl,
    import_manual_summary_text as import_manual_summary_text_impl,
    import_phone_usage_file as import_phone_usage_file_impl,
    run_phone_optimizer as run_phone_optimizer_impl,
)
from pip_workspace import (
    classify_action_permission as classify_action_permission_impl,
    condense_workspace as condense_workspace_impl,
    draft_next_actions as draft_next_actions_impl,
    export_control_status as export_control_status_impl,
    request_permission as request_permission_impl,
    resolve_permission as resolve_permission_impl,
    run_ambient_cycle as run_ambient_cycle_impl,
    scan_workspace as scan_workspace_impl,
    queue_next_wake as queue_next_wake_impl,
)


REQUIRED_USAGE_FIELDS = {
    "timestamp": str,
    "app_name": str,
    "event_type": str,
    "battery_delta": int,
    "notifications_received": int,
    "notifications_dismissed_unread": int,
    "session_duration_seconds": int,
}


@dataclass(frozen=True)
class SkillSpec:
    name: str
    description: str
    inputs: list[str]
    outputs: list[str]
    permissions: list[str] = field(default_factory=list)


def _write_json(path: str, data: dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def run_weekly_dream(args: argparse.Namespace) -> dict[str, Any]:
    engine = PipEngine(memory_path=args.memory)
    result = engine.run(args.input, feedback=args.feedback)
    if args.output:
        _write_json(args.output, result)
    return {
        "skill": "run_weekly_dream",
        "proposal_card": result["proposal_card"],
        "thermal_state": result["thermal_state"],
        "decision_trace": result["decision_trace"],
        "output": args.output,
    }


def inspect_memory(args: argparse.Namespace) -> dict[str, Any]:
    memory_path = Path(args.memory)
    if not memory_path.exists():
        return {
            "skill": "inspect_memory",
            "exists": False,
            "memory": None,
        }
    memory = json.loads(memory_path.read_text(encoding="utf-8"))
    return {
        "skill": "inspect_memory",
        "exists": True,
        "cycle_count": memory.get("cycle_count", 0),
        "tracked_tattoos": len(memory.get("tattoo_history", {})),
        "recent_proposals": memory.get("proposal_history", [])[-5:],
        "cooldowns": memory.get("cooldowns", {}),
        "compost_log": memory.get("compost_log", [])[-5:],
    }


def export_proposal_card(args: argparse.Namespace) -> dict[str, Any]:
    result = json.loads(Path(args.result).read_text(encoding="utf-8"))
    proposal = {
        "proposal_card": result.get("proposal_card", {}),
        "thermal_state": result.get("thermal_state", {}),
        "decision_trace": result.get("decision_trace", {}),
    }
    _write_json(args.output, proposal)
    return {
        "skill": "export_proposal_card",
        "output": args.output,
        "proposal_card": proposal["proposal_card"],
    }


def validate_android_usage(args: argparse.Namespace) -> dict[str, Any]:
    source = Path(args.input)
    raw = json.loads(source.read_text(encoding="utf-8"))
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
        "skill": "validate_android_usage",
        "input": str(source),
        "ok": not errors,
        "event_count": len(raw),
        "errors": errors,
        "warnings": warnings,
    }


def import_phone_usage(args: argparse.Namespace) -> dict[str, Any]:
    status = import_phone_usage_file_impl(args.input, run_optimizer=True)
    return {
        "skill": "import_phone_usage",
        "status": status,
    }


def import_phone_summary(args: argparse.Namespace) -> dict[str, Any]:
    text = Path(args.input).read_text(encoding="utf-8")
    status = import_manual_summary_text_impl(text, source_name=Path(args.input).name)
    return {
        "skill": "import_phone_summary",
        "status": status,
    }


def run_phone_optimizer(args: argparse.Namespace) -> dict[str, Any]:
    status = run_phone_optimizer_impl(feedback=args.feedback)
    return {
        "skill": "run_phone_optimizer",
        "status": status,
    }


def inspect_phone_status(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "skill": "inspect_phone_status",
        "status": get_phone_status_impl(),
    }


def apply_phone_feedback(args: argparse.Namespace) -> dict[str, Any]:
    status = apply_phone_feedback_impl(args.feedback or "deferred", args.note or "")
    return {
        "skill": "apply_phone_feedback",
        "status": status,
    }


def list_jobs(args: argparse.Namespace) -> dict[str, Any]:
    import pip_jobs
    return {
        "skill": "list_jobs",
        "jobs": pip_jobs.list_jobs(),
    }


def stop_job(args: argparse.Namespace) -> dict[str, Any]:
    import pip_jobs
    return {
        "skill": "stop_job",
        "result": pip_jobs.request_stop(args.job_id or ""),
    }


def inspect_app_skills(args: argparse.Namespace) -> dict[str, Any]:
    import pip_app_skills
    return {
        "skill": "inspect_app_skills",
        "assessment": pip_app_skills.assess_app(args.app or "Blender"),
    }


def award_app_skill_xp(args: argparse.Namespace) -> dict[str, Any]:
    import pip_app_skills
    app = pip_app_skills.award_app_xp(
        args.app or "Blender",
        int(args.amount or 10),
        domain=args.domain or "general",
        evidence=args.evidence or "",
    )
    return {
        "skill": "award_app_skill_xp",
        "app": app,
    }


def bootstrap_developer_shells(args: argparse.Namespace) -> dict[str, Any]:
    import pip_app_skills
    return {
        "skill": "bootstrap_developer_shells",
        "result": pip_app_skills.bootstrap_developer_shells(write_personas=True),
    }


def inspect_developer_shells(args: argparse.Namespace) -> dict[str, Any]:
    import pip_app_skills
    return {
        "skill": "inspect_developer_shells",
        "result": pip_app_skills.inspect_developer_shells(args.shell),
    }


def list_blender_recipes(args: argparse.Namespace) -> dict[str, Any]:
    import pip_blender_recipes
    return {
        "skill": "list_blender_recipes",
        "recipes": pip_blender_recipes.list_recipes(),
    }


def draft_blender_recipe(args: argparse.Namespace) -> dict[str, Any]:
    import pip_blender_recipes
    return {
        "skill": "draft_blender_recipe",
        "draft": pip_blender_recipes.draft_recipe(
            args.recipe or "simple_character_blockout",
            project=args.project or "",
            goal=args.goal or "",
        ),
    }


def record_blender_recipe_result(args: argparse.Namespace) -> dict[str, Any]:
    import pip_blender_recipes
    return {
        "skill": "record_blender_recipe_result",
        "result": pip_blender_recipes.record_result(
            args.draft_id or "",
            args.status or "practiced",
            note=args.note or "",
        ),
    }


def inspect_token_governor(args: argparse.Namespace) -> dict[str, Any]:
    import pip_token_guard
    return {
        "skill": "inspect_token_governor",
        "status": pip_token_guard.status(),
    }


def govern_interaction(args: argparse.Namespace) -> dict[str, Any]:
    import pip_token_guard
    text = args.content or args.query or ""
    return {
        "skill": "govern_interaction",
        "assessment": pip_token_guard.assess_interaction(
            text,
            intent=args.intent or "chat",
            source_type=args.source_type or "first_hand",
            source_name=args.source_name or "Pip CLI interaction",
        ),
    }


def record_token_event(args: argparse.Namespace) -> dict[str, Any]:
    import pip_token_guard
    return {
        "skill": "record_token_event",
        "status": pip_token_guard.record_event(
            args.intent or "skill",
            estimated_tokens=int(args.estimated_tokens or 0),
            actual_tokens=args.actual_tokens,
            saved_tokens=int(args.saved_tokens or 0),
            note=args.note or "",
        ),
    }


def inspect_platform(args: argparse.Namespace) -> dict[str, Any]:
    import pip_platform
    return {
        "skill": "inspect_platform",
        "platform": pip_platform.feature_status(),
    }


def import_android_usage(args: argparse.Namespace) -> dict[str, Any]:
    validation = validate_android_usage(args)
    if not validation["ok"]:
        return {
            "skill": "import_android_usage",
            "input": args.input,
            "output": args.output,
            "imported": False,
            "validation": validation,
        }

    source = Path(args.input)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, output)
    return {
        "skill": "import_android_usage",
        "input": str(source),
        "output": str(output),
        "imported": True,
        "validation": validation,
    }


def scan_workspace(args: argparse.Namespace) -> dict[str, Any]:
    scan = scan_workspace_impl(args.workspace, args.manifest)
    return {
        "skill": "scan_workspace",
        "workspace": scan["workspace"],
        "file_count": scan["file_count"],
        "draft_dir": scan["draft_dir"],
        "scan_path": str(Path(scan["draft_dir"]) / "workspace_scan.json"),
        "mode": scan["mode"],
    }


def condense_workspace(args: argparse.Namespace) -> dict[str, Any]:
    result = condense_workspace_impl(args.workspace, args.manifest)
    return {
        "skill": "condense_workspace",
        **result,
    }


def draft_next_actions(args: argparse.Namespace) -> dict[str, Any]:
    result = draft_next_actions_impl(args.workspace, args.manifest)
    return {
        "skill": "draft_next_actions",
        **result,
    }


def export_control_status(args: argparse.Namespace) -> dict[str, Any]:
    status = export_control_status_impl(args.workspace, args.manifest)
    return {
        "skill": "export_control_status",
        "status": status,
    }


def run_ambient_cycle(args: argparse.Namespace) -> dict[str, Any]:
    result = run_ambient_cycle_impl(args.workspace, args.wake_minutes, args.context, args.manifest)
    return {
        "skill": "run_ambient_cycle",
        **result,
    }


def queue_next_wake(args: argparse.Namespace) -> dict[str, Any]:
    state = queue_next_wake_impl(args.workspace, args.wake_minutes, args.context, args.manifest)
    return {
        "skill": "queue_next_wake",
        "ambient_state": state,
    }


def classify_action_permission(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "skill": "classify_action_permission",
        "classification": classify_action_permission_impl(args.action_type),
    }


def request_permission(args: argparse.Namespace) -> dict[str, Any]:
    request = request_permission_impl(
        args.workspace,
        args.action_type,
        args.title or f"Permission request for {args.action_type}",
        args.rationale or "Manual Pip permission request.",
        args.manifest,
    )
    return {
        "skill": "request_permission",
        "request": request,
    }


def resolve_permission(args: argparse.Namespace) -> dict[str, Any]:
    result = resolve_permission_impl(args.workspace, args.request_id, args.decision, args.note or "", args.manifest)
    return {
        "skill": "resolve_permission",
        "request": result,
    }


def trigger_pc_focus_mode(args: argparse.Namespace) -> dict[str, Any]:
    import pip_safety
    import pip_platform
    blocked = pip_safety.gate_skill(
        "trigger_pc_focus_mode",
        args,
        "Pip wants to minimize all windows as a PC focus-mode action.",
    )
    if blocked:
        return blocked

    if not pip_platform.is_windows():
        return {
            "skill": "trigger_pc_focus_mode",
            "ok": False,
            "message": "Focus mode is currently Windows-only.",
            "platform": pip_platform.feature_status(),
        }

    import subprocess
    try:
        subprocess.run(
            ["powershell", "-WindowStyle", "Hidden", "-Command", "(New-Object -ComObject Shell.Application).MinimizeAll()"],
            check=True,
        )
        ok = True
        msg = "Successfully activated Focus Mode (Minimized all windows)."
    except Exception as e:
        ok = False
        msg = f"Failed to activate Focus Mode: {e}"
        
    return {
        "skill": "trigger_pc_focus_mode",
        "ok": ok,
        "message": msg
    }


def run_pc_optimizer(args: argparse.Namespace) -> dict[str, Any]:
    import_dir = Path("imports")
    usage_files = list(import_dir.glob("pc_usage_*.json"))
    if not usage_files:
        return {
            "skill": "run_pc_optimizer",
            "ok": False,
            "message": "No PC usage files found in imports folder."
        }
        
    latest_file = max(usage_files, key=lambda p: p.stat().st_mtime)
    
    engine = PipEngine(memory_path="imports/pc_memory.json")
    result = engine.run(str(latest_file), feedback=getattr(args, "feedback", None))
    
    output_path = import_dir / "pc_proposal_card.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result["proposal_card"], indent=2), encoding="utf-8")
    
    return {
        "skill": "run_pc_optimizer",
        "ok": True,
        "proposal_card": result["proposal_card"],
        "thermal_state": result["thermal_state"],
        "source_file": str(latest_file)
    }


def search_brain(args: argparse.Namespace) -> dict[str, Any]:
    query = (getattr(args, "query", "") or "")
    try:
        import pip_hound
        results = pip_hound.search(query)
        return {
            "skill": "search_brain",
            "ok": True,
            "query": query,
            "matches": len(results),
            "results": results
        }
    except Exception as e:
        return {"skill": "search_brain", "ok": False, "message": str(e)}

def assess_hardware(args: argparse.Namespace) -> dict[str, Any]:
    try:
        import pip_hardware
        result = pip_hardware.assess_hardware()
        return {
            "skill": "assess_hardware",
            "ok": True,
            "hardware_scan": result
        }
    except Exception as e:
        return {"skill": "assess_hardware", "ok": False, "message": str(e)}

def generate_capsule(args: argparse.Namespace) -> dict[str, Any]:
    query = (getattr(args, "query", "") or "")
    try:
        import pip_hound
        out = pip_hound.capsule(query)
        if out:
            return {"skill": "generate_capsule", "ok": True, "capsule_path": out}
        return {"skill": "generate_capsule", "ok": False, "message": "No results found"}
    except Exception as e:
        return {"skill": "generate_capsule", "ok": False, "message": str(e)}

def read_brain_file(args: argparse.Namespace) -> dict[str, Any]:
    import pip_config
    brain_dir = pip_config.get_memory_path()
    target = getattr(args, "filename", "")
    results = list(brain_dir.rglob(target))
    if not results:
        return {"skill": "read_brain_file", "ok": False, "message": "File not found"}
    
    try:
        content = results[0].read_text(encoding="utf-8")
        return {
            "skill": "read_brain_file",
            "ok": True,
            "filename": results[0].name,
            "content": content[:5000] # Truncate to avoid memory blowup
        }
    except Exception as e:
        return {"skill": "read_brain_file", "ok": False, "message": str(e)}

def write_brain_file(args: argparse.Namespace) -> dict[str, Any]:
    import pip_config
    brain_dir = pip_config.get_memory_path().resolve()
    target = (brain_dir / getattr(args, "filename", "new_brain_file.txt")).resolve()
    
    if not target.is_relative_to(brain_dir):
        return {"skill": "write_brain_file", "ok": False, "message": "Security Error: Attempted to write outside the Pip memory sandbox."}
        
    if target.suffix not in [".txt", ".json", ".md", ".py"]:
        target = target.with_suffix(".txt")
        
    try:
        mode = "a" if target.exists() else "w"
        with open(target, mode, encoding="utf-8") as f:
            if mode == "a":
                f.write("\n")
            f.write(getattr(args, "content", ""))
        return {"skill": "write_brain_file", "ok": True, "filename": target.name}
    except Exception as e:
        return {"skill": "write_brain_file", "ok": False, "message": str(e)}

def run_python_script(args: argparse.Namespace) -> dict[str, Any]:
    import pip_safety
    blocked = pip_safety.gate_skill(
        "run_python_script",
        args,
        "Pip wants to write and launch a Python script inside the configured memory folder.",
    )
    if blocked:
        return blocked

    import subprocess
    import pip_config
    import sys
    from pathlib import Path
    
    script_code = getattr(args, "code", "")
    script_name = getattr(args, "name", "background_task.py")
    
    brain_dir = pip_config.get_memory_path().resolve()
    script_path = (brain_dir / script_name).resolve()
    
    if not script_path.is_relative_to(brain_dir):
        return {"skill": "run_python_script", "ok": False, "message": "Security Error: Attempted to execute script outside the Pip memory sandbox."}
        
    log_path = brain_dir / f"{script_path.stem}.log"
    
    try:
        script_path.write_text(script_code, encoding="utf-8")
        
        # Run in background via pythonw/subprocess detached
        if sys.platform == "win32":
            CREATE_NO_WINDOW = 0x08000000
            with open(log_path, "w") as out:
                subprocess.Popen(
                    [sys.executable, str(script_path)],
                    stdout=out,
                    stderr=out,
                    creationflags=CREATE_NO_WINDOW,
                    cwd=str(brain_dir)
                )
        else:
            with open(log_path, "w") as out:
                subprocess.Popen(
                    [sys.executable, str(script_path)],
                    stdout=out,
                    stderr=out,
                    cwd=str(brain_dir)
                )
                
        return {
            "skill": "run_python_script", 
            "ok": True, 
            "message": f"Script started in background. Logs will be written to {log_path.name}"
        }
    except Exception as e:
        return {"skill": "run_python_script", "ok": False, "message": str(e)}


def hands_type_text(args: argparse.Namespace) -> dict[str, Any]:
    import pip_safety
    blocked = pip_safety.gate_skill(
        "hands_type_text",
        args,
        "Pip wants to type text into the foreground app.",
    )
    if blocked:
        return blocked

    try:
        import pip_hands
        import pip_evolution
    except ImportError:
        return {"skill": "hands_type_text", "ok": False, "message": "Module not found."}
    
    text = getattr(args, "content", "")
    target_app = getattr(args, "target_app", "")
    
    if pip_hands.type_text(text):
        if target_app:
            xp_data = pip_evolution.award_xp(target_app, 5)
            return {"skill": "hands_type_text", "ok": True, "xp_data": xp_data}
        return {"skill": "hands_type_text", "ok": True}
    return {"skill": "hands_type_text", "ok": False, "message": "Typing failed or failsafe triggered."}

def hands_press_key(args: argparse.Namespace) -> dict[str, Any]:
    import pip_safety
    blocked = pip_safety.gate_skill(
        "hands_press_key",
        args,
        "Pip wants to press a keyboard key in the foreground app.",
    )
    if blocked:
        return blocked

    try:
        import pip_hands
        import pip_evolution
    except ImportError:
        return {"skill": "hands_press_key", "ok": False, "message": "Module not found."}
    
    key = getattr(args, "key", "")
    target_app = getattr(args, "target_app", "")
    
    if pip_hands.press_key(key):
        if target_app:
            xp_data = pip_evolution.award_xp(target_app, 2)
            return {"skill": "hands_press_key", "ok": True, "xp_data": xp_data}
        return {"skill": "hands_press_key", "ok": True}
    return {"skill": "hands_press_key", "ok": False, "message": "Key press failed or failsafe triggered."}

def hands_click_mouse(args: argparse.Namespace) -> dict[str, Any]:
    import pip_safety
    blocked = pip_safety.gate_skill(
        "hands_click_mouse",
        args,
        "Pip wants to click the mouse.",
    )
    if blocked:
        return blocked

    try:
        import pip_hands
        import pip_evolution
    except ImportError:
        return {"skill": "hands_click_mouse", "ok": False, "message": "Module not found."}
    
    x = getattr(args, "x", None)
    y = getattr(args, "y", None)
    target_app = getattr(args, "target_app", "")
    
    x_val = int(x) if x is not None else None
    y_val = int(y) if y is not None else None
    
    if pip_hands.click_mouse(x=x_val, y=y_val):
        if target_app:
            xp_data = pip_evolution.award_xp(target_app, 3)
            return {"skill": "hands_click_mouse", "ok": True, "xp_data": xp_data}
        return {"skill": "hands_click_mouse", "ok": True}
    return {"skill": "hands_click_mouse", "ok": False, "message": "Click failed."}

def record_new_macro(args: argparse.Namespace) -> dict[str, Any]:
    import pip_safety
    blocked = pip_safety.gate_skill(
        "record_new_macro",
        args,
        "Pip wants to record keyboard events until Escape is pressed.",
    )
    if blocked:
        return blocked

    try:
        import pip_hands
    except ImportError:
        return {"skill": "record_new_macro", "ok": False, "message": "pip_hands module not found."}
    
    from pathlib import Path
    import json
    
    events = pip_hands.record_macro(stop_key='esc')
    if not events:
        return {"skill": "record_new_macro", "ok": False, "message": "No events recorded or recording failed."}
        
    import pip_config
    import re
    brain_dir = pip_config.get_memory_path()
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", getattr(args, "name", "macro")).strip("._")
    if not name:
        name = "macro"
    target = brain_dir / f"macro_{name}.json"
    target.write_text(json.dumps(events, indent=2), encoding="utf-8")
    
    return {"skill": "record_new_macro", "ok": True, "filename": target.name, "event_count": len(events)}


SKILLS: dict[str, tuple[SkillSpec, Callable[[argparse.Namespace], dict[str, Any]]]] = {
    "inspect_platform": (
        SkillSpec(
            name="inspect_platform",
            description="Inspect OS compatibility and which Pip body/brain features are available on this machine.",
            inputs=[],
            outputs=["platform feature status JSON"],
            permissions=["read platform info"],
        ),
        inspect_platform,
    ),
    "list_jobs": (
        SkillSpec(
            name="list_jobs",
            description="List visible Pip background jobs, recent logs, and statuses.",
            inputs=[],
            outputs=["jobs/jobs.json with latest log snippets"],
            permissions=["read jobs folder"],
        ),
        list_jobs,
    ),
    "stop_job": (
        SkillSpec(
            name="stop_job",
            description="Request a cooperative stop for a running Pip job.",
            inputs=["--job-id id"],
            outputs=["updated job status"],
            permissions=["write jobs folder"],
        ),
        stop_job,
    ),
    "inspect_app_skills": (
        SkillSpec(
            name="inspect_app_skills",
            description="Inspect Pip's skill assessment profile for an app, defaulting to Blender.",
            inputs=["--app Blender"],
            outputs=["app skill profile and next focus areas"],
            permissions=["read memory folder"],
        ),
        inspect_app_skills,
    ),
    "award_app_skill_xp": (
        SkillSpec(
            name="award_app_skill_xp",
            description="Record evidence and XP for Pip's knowledge of an app domain.",
            inputs=["--app Blender", "--domain modeling", "--amount 10", "--evidence note"],
            outputs=["updated app skill profile"],
            permissions=["write memory folder"],
        ),
        award_app_skill_xp,
    ),
    "bootstrap_developer_shells": (
        SkillSpec(
            name="bootstrap_developer_shells",
            description="Install Pip's starter developer shells for Codex, Claude Code, and Antigravity.",
            inputs=[],
            outputs=["developer shell manifest, persona JSON files, and app skill profiles"],
            permissions=["write memory folder", "write local personas folder"],
        ),
        bootstrap_developer_shells,
    ),
    "inspect_developer_shells": (
        SkillSpec(
            name="inspect_developer_shells",
            description="Inspect Pip's known developer shells and their app skill progress.",
            inputs=["--shell optional codex|claude|anti"],
            outputs=["developer shell profiles and persona status"],
            permissions=["read memory folder", "read local personas folder"],
        ),
        inspect_developer_shells,
    ),
    "list_blender_recipes": (
        SkillSpec(
            name="list_blender_recipes",
            description="List safe draft-only Blender task recipes and recent drafts.",
            inputs=[],
            outputs=["available Blender recipes and recent draft history"],
            permissions=["read memory folder"],
        ),
        list_blender_recipes,
    ),
    "draft_blender_recipe": (
        SkillSpec(
            name="draft_blender_recipe",
            description="Draft a safe Blender task recipe into Pip memory without controlling Blender.",
            inputs=["--recipe simple_character_blockout", "--project optional", "--goal optional"],
            outputs=["blender_recipes/*.json draft plan"],
            permissions=["write memory folder"],
        ),
        draft_blender_recipe,
    ),
    "record_blender_recipe_result": (
        SkillSpec(
            name="record_blender_recipe_result",
            description="Record practice/completion feedback for a Blender recipe draft and update app skill XP.",
            inputs=["--draft-id id", "--status practiced|completed|deferred|needs_revision", "--note optional"],
            outputs=["updated recipe index and Blender app skill profile"],
            permissions=["write memory folder"],
        ),
        record_blender_recipe_result,
    ),
    "inspect_token_governor": (
        SkillSpec(
            name="inspect_token_governor",
            description="Inspect Pip's Token Governor pressure, budget, recent events, and Signal Sieve bridge status.",
            inputs=[],
            outputs=["token governor status JSON"],
            permissions=["read memory folder"],
        ),
        inspect_token_governor,
    ),
    "govern_interaction": (
        SkillSpec(
            name="govern_interaction",
            description="Assess a user/Pip interaction through Signal Sieve and the local token governor before spending effort.",
            inputs=["--content text", "--intent chat|autonomous_goal|blender_recipe"],
            outputs=["admission decision, mode, priority, budget, nudge"],
            permissions=["read/write memory folder", "read local signal-sieve code"],
        ),
        govern_interaction,
    ),
    "record_token_event": (
        SkillSpec(
            name="record_token_event",
            description="Record estimated/actual/saved token usage into Pip's governor memory.",
            inputs=["--intent chat", "--estimated-tokens 100", "--actual-tokens 80", "--saved-tokens 20"],
            outputs=["updated token governor status"],
            permissions=["write memory folder"],
        ),
        record_token_event,
    ),
    "search_brain": (
        SkillSpec(
            name="search_brain",
            description="Search the Brain folder using the Text Hound FTS5 index for extremely fast snippet retrieval.",
            inputs=["--query text"],
            outputs=["list of matching filenames and snippets"],
            permissions=["read brain folder"],
        ),
        search_brain,
    ),
    "assess_hardware": (
        SkillSpec(
            name="assess_hardware",
            description="Scans available hardware info to recommend the optimal local language model.",
            inputs=[],
            outputs=["hardware analysis and model recommendation"],
            permissions=["read platform hardware info"],
        ),
        assess_hardware,
    ),
    "generate_capsule": (
        SkillSpec(
            name="generate_capsule",
            description="Uses Text Hound to build a draft Markdown capsule summarizing search results.",
            inputs=["--query text"],
            outputs=["capsule file path"],
            permissions=["read brain folder", "write capsule file"],
        ),
        generate_capsule,
    ),
    "read_brain_file": (
        SkillSpec(
            name="read_brain_file",
            description="Read the contents of a specific file in the Brain folder.",
            inputs=["--filename name"],
            outputs=["file content (truncated)"],
            permissions=["read brain file"],
        ),
        read_brain_file,
    ),
    "write_brain_file": (
        SkillSpec(
            name="write_brain_file",
            description="Write or append content to a file in the Brain folder.",
            inputs=["--filename name", "--content text"],
            outputs=["success status"],
            permissions=["write brain file"],
        ),
        write_brain_file,
    ),
    "hands_type_text": (
        SkillSpec(
            name="hands_type_text",
            description="Type text out via pyautogui.",
            inputs=["--content text", "--target-app app_name"],
            outputs=["success or xp_data"],
            permissions=["automate ui"],
        ),
        hands_type_text,
    ),
    "run_python_script": (
        SkillSpec(
            name="run_python_script",
            description="Write and execute a Python script in the background to handle heavy compute or repetitive tasks. Results are written to a log file.",
            inputs=["--name script.py", "--code text"],
            outputs=["status message and log filename"],
            permissions=["execute arbitrary code"],
        ),
        run_python_script,
    ),
    "hands_press_key": (
        SkillSpec(
            name="hands_press_key",
            description="Press a specific key via pyautogui (e.g. enter, tab, win).",
            inputs=["--key keyname", "--target-app app_name"],
            outputs=["success or xp_data"],
            permissions=["automate ui"],
        ),
        hands_press_key,
    ),
    "hands_click_mouse": (
        SkillSpec(
            name="hands_click_mouse",
            description="Click the mouse at current location or specified x, y.",
            inputs=["--x x_coord", "--y y_coord", "--target-app app_name"],
            outputs=["success or xp_data"],
            permissions=["automate ui"],
        ),
        hands_click_mouse,
    ),
    "record_new_macro": (
        SkillSpec(
            name="record_new_macro",
            description="Watch and learn: records keystrokes until 'esc' is pressed, saving to a brain macro file.",
            inputs=["--name name"],
            outputs=["saved macro filename"],
            permissions=["record keyboard", "write brain file"],
        ),
        record_new_macro,
    ),
    "trigger_pc_focus_mode": (
        SkillSpec(
            name="trigger_pc_focus_mode",
            description="Activates focus mode where an OS window-management adapter is available.",
            inputs=[],
            outputs=["success message JSON"],
            permissions=["run OS window-management command"],
        ),
        trigger_pc_focus_mode,
    ),
    "run_pc_optimizer": (
        SkillSpec(
            name="run_pc_optimizer",
            description="Run Pip's PC optimization engine over the latest PC usage JSON.",
            inputs=["--feedback optional"],
            outputs=["imports/pc_proposal_card.json"],
            permissions=["read/write imports folder"],
        ),
        run_pc_optimizer,
    ),
    "run_weekly_dream": (
        SkillSpec(
            name="run_weekly_dream",
            description="Run Pip over a one-week usage file and update local memory.",
            inputs=["--input usage.json", "--memory memory.json", "--feedback optional"],
            outputs=["proposal result JSON"],
            permissions=["read usage file", "write memory file", "optional write output file"],
        ),
        run_weekly_dream,
    ),
    "inspect_memory": (
        SkillSpec(
            name="inspect_memory",
            description="Summarize Pip memory without modifying it.",
            inputs=["--memory memory.json"],
            outputs=["memory summary JSON"],
            permissions=["read memory file"],
        ),
        inspect_memory,
    ),
    "export_proposal_card": (
        SkillSpec(
            name="export_proposal_card",
            description="Extract the proposal card from a full Pip run result.",
            inputs=["--result result.json", "--output proposal_card.json"],
            outputs=["proposal card JSON"],
            permissions=["read result file", "write output file"],
        ),
        export_proposal_card,
    ),
    "import_android_usage": (
        SkillSpec(
            name="import_android_usage",
            description="Copy a normalized Android usage export into Pip's input area.",
            inputs=["--input android_usage.json", "--output usage.json"],
            outputs=["usage JSON"],
            permissions=["read Android export", "write normalized usage file"],
        ),
        import_android_usage,
    ),
    "validate_android_usage": (
        SkillSpec(
            name="validate_android_usage",
            description="Validate a normalized Android usage export before Pip reads it.",
            inputs=["--input android_usage.json"],
            outputs=["validation JSON"],
            permissions=["read Android export"],
        ),
        validate_android_usage,
    ),
    "import_phone_usage": (
        SkillSpec(
            name="import_phone_usage",
            description="Import an S25 usage JSON file, validate it, run the phone optimizer, and update phone bridge status.",
            inputs=["--input s25_usage_last_7_days.json"],
            outputs=["imports/s25_usage_last_7_days.json, s25_latest_dream.json, s25_proposal_card.json, phone_bridge_status.json"],
            permissions=["read input file", "write imports folder"],
        ),
        import_phone_usage,
    ),
    "run_phone_optimizer": (
        SkillSpec(
            name="run_phone_optimizer",
            description="Run Pip's phone optimization engine over the latest imported S25 usage JSON.",
            inputs=["--feedback optional"],
            outputs=["imports/s25_latest_dream.json, s25_proposal_card.json, phone_bridge_status.json"],
            permissions=["read/write imports folder"],
        ),
        run_phone_optimizer,
    ),
    "import_phone_summary": (
        SkillSpec(
            name="import_phone_summary",
            description="Import a manual S25 app summary CSV and convert it into normalized phone usage events.",
            inputs=["--input phone_summary.csv"],
            outputs=["imports/s25_usage_last_7_days.json, phone bridge proposal/status files"],
            permissions=["read input file", "write imports folder"],
        ),
        import_phone_summary,
    ),
    "inspect_phone_status": (
        SkillSpec(
            name="inspect_phone_status",
            description="Inspect the latest S25 bridge status and proposal.",
            inputs=[],
            outputs=["phone bridge status JSON"],
            permissions=["read imports folder"],
        ),
        inspect_phone_status,
    ),
    "apply_phone_feedback": (
        SkillSpec(
            name="apply_phone_feedback",
            description="Apply feedback to the latest phone optimization proposal and rerun memory update.",
            inputs=["--feedback accepted|rejected|deferred|resolved", "--note optional"],
            outputs=["updated imports/s25_memory.json and phone_bridge_status.json"],
            permissions=["read/write imports folder"],
        ),
        apply_phone_feedback,
    ),
    "scan_workspace": (
        SkillSpec(
            name="scan_workspace",
            description="Scan an approved workspace and write a draft-only inventory.",
            inputs=["--workspace garden_spiders", "--manifest approved_workspaces.json"],
            outputs=["workspace_scan.json under the approved draft folder"],
            permissions=["read approved workspace files", "write approved draft folder only"],
        ),
        scan_workspace,
    ),
    "condense_workspace": (
        SkillSpec(
            name="condense_workspace",
            description="Create a compact project digest for an approved workspace.",
            inputs=["--workspace garden_spiders", "--manifest approved_workspaces.json"],
            outputs=["project_digest.md and memory_update.json under the approved draft folder"],
            permissions=["read approved workspace files", "write approved draft folder only"],
        ),
        condense_workspace,
    ),
    "draft_next_actions": (
        SkillSpec(
            name="draft_next_actions",
            description="Draft the next three supervised actions and latest proposal card for an approved workspace.",
            inputs=["--workspace garden_spiders", "--manifest approved_workspaces.json"],
            outputs=["next_3_tasks.json, proposal_card.json, memory_update.json, control_status.json"],
            permissions=["read approved workspace files", "write approved draft folder only"],
        ),
        draft_next_actions,
    ),
    "export_control_status": (
        SkillSpec(
            name="export_control_status",
            description="Export the latest phone-control status for an approved workspace.",
            inputs=["--workspace garden_spiders", "--manifest approved_workspaces.json"],
            outputs=["control status JSON"],
            permissions=["read approved draft folder", "write control_status.json"],
        ),
        export_control_status,
    ),
    "run_ambient_cycle": (
        SkillSpec(
            name="run_ambient_cycle",
            description="Run one supervised draft-only ambient cycle for an approved workspace.",
            inputs=["--workspace garden_spiders", "--wake-minutes 30", "--context optional"],
            outputs=["ambient transcript, ambient_state.json, refreshed draft artifacts"],
            permissions=["read approved workspace files", "write approved draft folder only"],
        ),
        run_ambient_cycle,
    ),
    "queue_next_wake": (
        SkillSpec(
            name="queue_next_wake",
            description="Set Pip's next ambient wake time without running a cycle.",
            inputs=["--workspace garden_spiders", "--wake-minutes 30", "--context optional"],
            outputs=["ambient_state.json"],
            permissions=["write approved draft folder only"],
        ),
        queue_next_wake,
    ),
    "classify_action_permission": (
        SkillSpec(
            name="classify_action_permission",
            description="Classify a proposed action as auto-allowed or requiring permission.",
            inputs=["--action-type code_edit"],
            outputs=["permission classification JSON"],
            permissions=["none"],
        ),
        classify_action_permission,
    ),
    "request_permission": (
        SkillSpec(
            name="request_permission",
            description="Add a permission request to the workspace review queue.",
            inputs=["--workspace garden_spiders", "--action-type code_edit", "--title text", "--rationale text"],
            outputs=["permission_queue.json"],
            permissions=["write approved draft folder only"],
        ),
        request_permission,
    ),
    "resolve_permission": (
        SkillSpec(
            name="resolve_permission",
            description="Approve or deny a pending permission request.",
            inputs=["--workspace garden_spiders", "--request-id id", "--decision approved|denied", "--note optional"],
            outputs=["permission_queue.json"],
            permissions=["write approved draft folder only"],
        ),
        resolve_permission,
    ),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run small local Pip skills.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="List available skills")

    run_parser = subparsers.add_parser("run", help="Run one skill")
    run_parser.add_argument("skill", choices=sorted(SKILLS))
    run_parser.add_argument("--input", help="Input usage or Android export JSON")
    run_parser.add_argument("--memory", default="memory.json", help="Pip memory JSON path")
    run_parser.add_argument("--feedback", choices=["accepted", "rejected", "deferred", "resolved"])
    run_parser.add_argument("--output", help="Output JSON path")
    run_parser.add_argument("--result", help="Full Pip result JSON for export_proposal_card")
    run_parser.add_argument("--workspace", default="garden_spiders", help="Approved workspace key")
    run_parser.add_argument("--manifest", default="approved_workspaces.json", help="Approved workspace manifest path")
    run_parser.add_argument("--wake-minutes", type=int, default=30, help="Minutes until next ambient wake")
    run_parser.add_argument("--context", default="Run the next supervised draft-only ambient cycle.", help="Next ambient wake context")
    run_parser.add_argument("--action-type", default="read_workspace", help="Permission classifier action type")
    run_parser.add_argument("--title", help="Permission request title")
    run_parser.add_argument("--rationale", help="Permission request rationale")
    run_parser.add_argument("--request-id", help="Pending permission request id")
    run_parser.add_argument("--decision", choices=["approved", "denied"], help="Permission decision")
    run_parser.add_argument("--note", help="Optional permission decision note")
    run_parser.add_argument("--query", help="Query string for search_brain")
    run_parser.add_argument("--filename", help="Filename for read/write brain file")
    run_parser.add_argument("--content", help="Content to write to brain file")
    run_parser.add_argument("--name", help="Name for recorded macro")
    run_parser.add_argument("--key", help="Key name for hands_press_key")
    run_parser.add_argument("--x", help="X coordinate for hands_click_mouse")
    run_parser.add_argument("--y", help="Y coordinate for hands_click_mouse")
    run_parser.add_argument("--target-app", help="Target App Name for Persona Evolution XP")
    run_parser.add_argument("--approved-request-id", help="Approved one-use permission request id for high-risk skills")
    run_parser.add_argument("--job-id", help="Pip job id for stop_job")
    run_parser.add_argument("--app", help="Application name for app skill assessment")
    run_parser.add_argument("--shell", help="Developer shell name for inspect_developer_shells")
    run_parser.add_argument("--domain", help="Application skill domain, such as modeling or animation")
    run_parser.add_argument("--amount", type=int, help="XP amount for award_app_skill_xp")
    run_parser.add_argument("--evidence", help="Evidence note for app skill progress")
    run_parser.add_argument("--recipe", help="Blender recipe key for draft_blender_recipe")
    run_parser.add_argument("--project", help="Project/context name for Blender recipe drafts")
    run_parser.add_argument("--goal", help="Goal text for Blender recipe drafts")
    run_parser.add_argument("--draft-id", help="Blender recipe draft id for recording results")
    run_parser.add_argument(
        "--status",
        choices=["practiced", "completed", "deferred", "needs_revision"],
        help="Status for record_blender_recipe_result",
    )
    run_parser.add_argument("--intent", help="Token Governor interaction intent")
    run_parser.add_argument("--source-type", help="Signal Sieve source type hint")
    run_parser.add_argument("--source-name", help="Signal Sieve source name hint")
    run_parser.add_argument("--estimated-tokens", type=int, help="Estimated tokens for record_token_event")
    run_parser.add_argument("--actual-tokens", type=int, help="Actual tokens for record_token_event")
    run_parser.add_argument("--saved-tokens", type=int, help="Saved/avoided tokens for record_token_event")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "list":
        payload = {
            name: asdict(spec)
            for name, (spec, _) in sorted(SKILLS.items())
        }
        print(json.dumps(payload, indent=2))
        return

    spec, handler = SKILLS[args.skill]
    missing: list[str] = []
    if args.skill in {
        "run_weekly_dream",
        "import_android_usage",
        "validate_android_usage",
        "import_phone_usage",
        "import_phone_summary",
    } and not args.input:
        missing.append("--input")
    if args.skill in {"run_weekly_dream", "export_proposal_card", "import_android_usage"} and not args.output:
        missing.append("--output")
    if args.skill == "export_proposal_card" and not args.result:
        missing.append("--result")
    if args.skill == "resolve_permission" and not args.request_id:
        missing.append("--request-id")
    if args.skill == "resolve_permission" and not args.decision:
        missing.append("--decision")
    if missing:
        parser.error(f"{args.skill} requires: {', '.join(missing)}")

    result = handler(args)
    result["skill_spec"] = asdict(spec)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
