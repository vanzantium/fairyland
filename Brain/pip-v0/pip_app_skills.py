#!/usr/bin/env python3
from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pip_config


ROOT = Path(__file__).resolve().parent


DEFAULT_BLENDER_DOMAINS = {
    "navigation": {
        "label": "Viewport Navigation",
        "level": 1,
        "xp": 0,
        "evidence": [],
        "next_steps": ["Pan, orbit, zoom, and frame selected reliably."],
    },
    "modeling": {
        "label": "Modeling",
        "level": 1,
        "xp": 0,
        "evidence": [],
        "next_steps": ["Create, transform, and organize basic mesh primitives."],
    },
    "materials": {
        "label": "Materials",
        "level": 1,
        "xp": 0,
        "evidence": [],
        "next_steps": ["Assign simple materials and name them consistently."],
    },
    "animation": {
        "label": "Animation",
        "level": 1,
        "xp": 0,
        "evidence": [],
        "next_steps": ["Set keyframes and explain timing changes."],
    },
    "python_automation": {
        "label": "Python Automation",
        "level": 1,
        "xp": 0,
        "evidence": [],
        "next_steps": ["Draft safe Blender Python scripts for reviewed execution."],
    },
    "render_pipeline": {
        "label": "Render Pipeline",
        "level": 1,
        "xp": 0,
        "evidence": [],
        "next_steps": ["Configure camera, lighting, and render settings for previews."],
    },
}

DEFAULT_DEVELOPER_SHELLS: dict[str, dict[str, Any]] = {
    "Codex": {
        "enabled": True,
        "role": "local codebase implementation and review teammate",
        "persona": "codex",
        "window_title": "Codex",
        "aliases": ["codex", "code", "openai codex"],
        "handoff_guidance": [
            "Use for precise local edits, test loops, reviews, and handoff bundles.",
            "Keep tasks scoped to a repository or approved workspace.",
            "Never ask Codex to mutate files outside an approved workspace without permission.",
        ],
        "domains": {
            "repo_mapping": {
                "label": "Repo Mapping",
                "level": 1,
                "xp": 0,
                "evidence": [],
                "next_steps": ["Inspect project structure before proposing edits."],
            },
            "patching": {
                "label": "Safe Patching",
                "level": 1,
                "xp": 0,
                "evidence": [],
                "next_steps": ["Prefer small reviewable patches and preserve user changes."],
            },
            "test_loop": {
                "label": "Test Loop",
                "level": 1,
                "xp": 0,
                "evidence": [],
                "next_steps": ["Run targeted checks after each code change."],
            },
            "handoff_review": {
                "label": "Handoff Review",
                "level": 1,
                "xp": 0,
                "evidence": [],
                "next_steps": ["Summarize risks, verification, and next actions clearly."],
            },
        },
    },
    "Claude Code": {
        "enabled": True,
        "role": "large-context planning, refactor reasoning, and code-review partner",
        "persona": "claude",
        "window_title": "Claude",
        "aliases": ["claude", "claude code", "anthropic claude"],
        "handoff_guidance": [
            "Use for long-context synthesis, architecture review, and careful refactor planning.",
            "Prefer asking for tradeoffs and failure modes before implementation.",
            "Treat execution or app control as a separate permission-gated step.",
        ],
        "domains": {
            "architecture_review": {
                "label": "Architecture Review",
                "level": 1,
                "xp": 0,
                "evidence": [],
                "next_steps": ["Ask Claude Code for structural tradeoffs and failure modes."],
            },
            "long_context_synthesis": {
                "label": "Long Context Synthesis",
                "level": 1,
                "xp": 0,
                "evidence": [],
                "next_steps": ["Use for dense docs and multi-file reasoning before implementation."],
            },
            "refactor_planning": {
                "label": "Refactor Planning",
                "level": 1,
                "xp": 0,
                "evidence": [],
                "next_steps": ["Draft staged refactor plans before any automated edits."],
            },
            "safety_review": {
                "label": "Safety Review",
                "level": 1,
                "xp": 0,
                "evidence": [],
                "next_steps": ["Use for permission, autonomy, and user-protection review."],
            },
        },
    },
    "Antigravity": {
        "enabled": True,
        "role": "agentic build/test exploration shell for supervised development",
        "persona": "anti",
        "window_title": "Antigravity",
        "aliases": ["anti", "antigravity", "google antigravity"],
        "handoff_guidance": [
            "Use for bounded agentic exploration, UI validation, and build iteration.",
            "Give it narrow tasks with visible outputs and a stop condition.",
            "Review its changes before Pip records them as trusted evidence.",
        ],
        "domains": {
            "agent_tasking": {
                "label": "Agent Tasking",
                "level": 1,
                "xp": 0,
                "evidence": [],
                "next_steps": ["Keep Antigravity tasks narrow, bounded, and observable."],
            },
            "ui_validation": {
                "label": "UI Validation",
                "level": 1,
                "xp": 0,
                "evidence": [],
                "next_steps": ["Use for supervised app/browser validation, not unbounded automation."],
            },
            "build_iteration": {
                "label": "Build Iteration",
                "level": 1,
                "xp": 0,
                "evidence": [],
                "next_steps": ["Record what Antigravity changed and what tests proved it."],
            },
            "agent_observation": {
                "label": "Agent Observation",
                "level": 1,
                "xp": 0,
                "evidence": [],
                "next_steps": ["Track when autonomous behavior helped, drifted, or needed correction."],
            },
        },
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def profile_path() -> Path:
    return pip_config.get_memory_path() / "app_skill_profiles.json"


def _empty_profile() -> dict[str, Any]:
    return {"version": 1, "apps": {}}


def load_profiles() -> dict[str, Any]:
    path = profile_path()
    if not path.exists():
        profiles = _empty_profile()
        ensure_app_profile("Blender", profiles)
        save_profiles(profiles)
        return profiles
    try:
        profiles = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        profiles = _empty_profile()
    profiles.setdefault("version", 1)
    profiles.setdefault("apps", {})
    ensure_app_profile("Blender", profiles)
    for shell_name in DEFAULT_DEVELOPER_SHELLS:
        ensure_app_profile(shell_name, profiles)
    save_profiles(profiles)
    return profiles


def save_profiles(profiles: dict[str, Any]) -> None:
    path = profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profiles, indent=2), encoding="utf-8")


def ensure_app_profile(app_name: str, profiles: dict[str, Any] | None = None) -> dict[str, Any]:
    profiles = profiles if profiles is not None else load_profiles()
    apps = profiles.setdefault("apps", {})
    key = app_name.strip() or "Unknown App"
    if key not in apps:
        apps[key] = {
            "app_name": key,
            "enabled": key.lower() == "blender",
            "level": 1,
            "xp": 0,
            "role": "general app teammate",
            "domains": {},
            "assessment_log": [],
            "updated_at": utc_now(),
        }
    if key.lower() == "blender":
        apps[key]["role"] = "small-scale animation team assistant"
        domains = apps[key].setdefault("domains", {})
        for domain, spec in DEFAULT_BLENDER_DOMAINS.items():
            domains.setdefault(domain, deepcopy(spec))
    for shell_name, shell in DEFAULT_DEVELOPER_SHELLS.items():
        if key.lower() == shell_name.lower():
            app = apps[key]
            app["enabled"] = shell.get("enabled", True)
            app["role"] = shell["role"]
            app["persona"] = shell["persona"]
            app["window_title"] = shell["window_title"]
            app["shell_type"] = "developer_tool"
            app["safety_mode"] = "approval_required_for_ui_handoff"
            domains = app.setdefault("domains", {})
            for domain, spec in shell["domains"].items():
                domains.setdefault(domain, deepcopy(spec))
    return apps[key]


def award_app_xp(app_name: str, amount: int, domain: str = "general", evidence: str = "") -> dict[str, Any]:
    profiles = load_profiles()
    app = ensure_app_profile(app_name, profiles)
    app["xp"] = app.get("xp", 0) + amount
    level_ups = app["xp"] // 100
    app["level"] = app.get("level", 1) + level_ups
    app["xp"] = app["xp"] % 100

    domains = app.setdefault("domains", {})
    domain_profile = domains.setdefault(
        domain,
        {"label": domain.replace("_", " ").title(), "level": 1, "xp": 0, "evidence": [], "next_steps": []},
    )
    domain_profile["xp"] = domain_profile.get("xp", 0) + amount
    domain_level_ups = domain_profile["xp"] // 100
    domain_profile["level"] = domain_profile.get("level", 1) + domain_level_ups
    domain_profile["xp"] = domain_profile["xp"] % 100
    if evidence:
        domain_profile.setdefault("evidence", []).append({"at": utc_now(), "note": evidence})
        domain_profile["evidence"] = domain_profile["evidence"][-10:]

    app.setdefault("assessment_log", []).append(
        {
            "at": utc_now(),
            "domain": domain,
            "xp": amount,
            "evidence": evidence,
            "app_level": app["level"],
            "domain_level": domain_profile["level"],
        }
    )
    app["assessment_log"] = app["assessment_log"][-50:]
    app["updated_at"] = utc_now()
    save_profiles(profiles)
    return app


def assess_app(app_name: str = "Blender") -> dict[str, Any]:
    profiles = load_profiles()
    app = ensure_app_profile(app_name, profiles)
    domains = app.get("domains", {})
    weakest = sorted(domains.items(), key=lambda item: (item[1].get("level", 1), item[1].get("xp", 0)))
    next_focus = []
    for _, domain in weakest[:3]:
        next_focus.extend(domain.get("next_steps", [])[:1])
    return {
        "app": app,
        "summary": {
            "app_name": app.get("app_name"),
            "role": app.get("role"),
            "level": app.get("level", 1),
            "xp": app.get("xp", 0),
            "domain_count": len(domains),
            "next_focus": next_focus,
        },
    }


def list_profiles() -> dict[str, Any]:
    profiles = load_profiles()
    return {
        "version": profiles.get("version", 1),
        "apps": list(profiles.get("apps", {}).values()),
    }


def list_developer_shells() -> dict[str, Any]:
    profiles = load_profiles()
    apps = profiles.get("apps", {})
    shells = []
    for shell_name, shell in DEFAULT_DEVELOPER_SHELLS.items():
        app = next(
            (value for key, value in apps.items() if key.lower() == shell_name.lower()),
            ensure_app_profile(shell_name, profiles),
        )
        shells.append(
            {
                "name": app.get("app_name", shell_name),
                "persona": shell["persona"],
                "aliases": shell.get("aliases", []),
                "role": app.get("role", shell["role"]),
                "enabled": app.get("enabled", True),
                "level": app.get("level", 1),
                "xp": app.get("xp", 0),
                "domains": app.get("domains", {}),
                "safety_mode": app.get("safety_mode", "approval_required_for_ui_handoff"),
                "handoff_guidance": shell.get("handoff_guidance", []),
            }
        )
    save_profiles(profiles)
    return {"shells": shells}


def persona_path(shell_name: str) -> Path:
    shell = DEFAULT_DEVELOPER_SHELLS[shell_name]
    return ROOT / "personas" / f"{shell['persona']}.json"


def developer_shell_manifest_path() -> Path:
    return pip_config.get_memory_path() / "developer_shells.json"


def persona_config(shell_name: str) -> dict[str, Any]:
    shell = DEFAULT_DEVELOPER_SHELLS[shell_name]
    capabilities = [
        domain.get("label", key.replace("_", " ").title())
        for key, domain in shell.get("domains", {}).items()
    ]
    return {
        "name": shell["persona"],
        "app_name": shell_name,
        "window_title": shell["window_title"],
        "description": f"{shell_name} developer shell. {shell['role']}.",
        "shell_type": "developer_tool",
        "safety_mode": "approval_required_for_ui_handoff",
        "aliases": shell.get("aliases", []),
        "capabilities": capabilities,
        "handoff_guidance": shell.get("handoff_guidance", []),
        "macros": {
            "focus_only": [
                {"action": "focus_window"}
            ],
            "submit_task": [
                {"action": "focus_window"},
                {"action": "type_text", "source": "task_input"},
                {"action": "press_key", "key": "enter"},
            ],
        },
    }


def developer_shell_app_entries() -> list[dict[str, Any]]:
    return [
        {
            "name": shell_name,
            "publisher": "Pip developer shell",
            "enabled": bool(shell.get("enabled", True)),
            "level": 1,
            "xp": 0,
            "shell_type": "developer_tool",
            "persona": shell["persona"],
        }
        for shell_name, shell in DEFAULT_DEVELOPER_SHELLS.items()
    ]


def _ensure_shell_apps_file() -> Path:
    apps_path = pip_config.get_memory_path() / "apps.json"
    apps_path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict[str, Any]] = []
    if apps_path.exists():
        try:
            raw = json.loads(apps_path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                existing = [item for item in raw if isinstance(item, dict)]
        except Exception:
            existing = []

    by_name = {str(item.get("name", "")): item for item in existing if item.get("name")}
    for entry in developer_shell_app_entries():
        current = by_name.setdefault(entry["name"], {})
        current.update({key: value for key, value in entry.items() if key not in {"level", "xp"}})
        current.setdefault("level", entry["level"])
        current.setdefault("xp", entry["xp"])
    apps = sorted(by_name.values(), key=lambda item: str(item.get("name", "")).lower())
    apps_path.write_text(json.dumps(apps, indent=2), encoding="utf-8")
    return apps_path


def bootstrap_developer_shells(write_personas: bool = True) -> dict[str, Any]:
    profiles = load_profiles()
    written_personas: list[str] = []
    for shell_name in DEFAULT_DEVELOPER_SHELLS:
        ensure_app_profile(shell_name, profiles)
        if write_personas:
            path = persona_path(shell_name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(persona_config(shell_name), indent=2), encoding="utf-8")
            written_personas.append(str(path))
    save_profiles(profiles)

    apps_path = _ensure_shell_apps_file()
    shell_manifest = {
        "version": 1,
        "generated_at": utc_now(),
        "safety_mode": "approval_required_for_ui_handoff",
        **list_developer_shells(),
    }
    manifest_path = developer_shell_manifest_path()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(shell_manifest, indent=2), encoding="utf-8")

    return {
        "generated_at": shell_manifest["generated_at"],
        "shell_count": len(DEFAULT_DEVELOPER_SHELLS),
        "manifest": str(manifest_path),
        "apps": str(apps_path),
        "personas": written_personas,
        "shells": shell_manifest["shells"],
    }


def inspect_developer_shells(shell: str | None = None) -> dict[str, Any]:
    data = list_developer_shells()
    if not shell:
        manifest = developer_shell_manifest_path()
        return {
            **data,
            "manifest": str(manifest),
            "manifest_exists": manifest.exists(),
        }

    needle = shell.strip().lower()
    for item in data.get("shells", []):
        names = [item.get("name", ""), item.get("persona", ""), *item.get("aliases", [])]
        if any(str(name).lower() == needle for name in names):
            return {
                "shell": item,
                "persona_path": str(persona_path(item["name"])),
                "persona_exists": persona_path(item["name"]).exists(),
                "manifest": str(developer_shell_manifest_path()),
            }
    return {
        "shell": None,
        "known_shells": [item.get("name") for item in data.get("shells", [])],
    }
