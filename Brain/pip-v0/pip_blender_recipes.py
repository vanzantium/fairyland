#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pip_app_skills
import pip_config


RECIPES: dict[str, dict[str, Any]] = {
    "simple_character_blockout": {
        "title": "Simple Character Blockout",
        "domain": "modeling",
        "intent": "Create a rough character silhouette using only primitive shapes.",
        "estimated_minutes": 20,
        "steps": [
            "Collect one reference image or write a one-sentence character prompt.",
            "Use a cube/cylinder/sphere-only blockout for head, torso, limbs, and major props.",
            "Name objects with clear prefixes such as body_head, body_torso, prop_staff.",
            "Check the silhouette from front, side, and three-quarter views.",
            "Save a screenshot or note what needs proportion cleanup next.",
        ],
        "success_checks": [
            "Scene contains named primitive objects only.",
            "Character reads clearly in silhouette.",
            "No destructive edits or external exports are required.",
        ],
    },
    "bounce_keyframe_test": {
        "title": "Bounce Keyframe Test",
        "domain": "animation",
        "intent": "Practice timing with one bouncing object and readable keyframes.",
        "estimated_minutes": 15,
        "steps": [
            "Create or select one simple sphere.",
            "Set a start keyframe at frame 1.",
            "Set a high point keyframe around frame 20.",
            "Set a squash/contact keyframe around frame 35.",
            "Play the timeline and write one timing note before changing anything else.",
        ],
        "success_checks": [
            "Timeline has at least three intentional keyframes.",
            "The motion can be described in one sentence.",
            "The test remains isolated from larger production files.",
        ],
    },
    "material_mood_pass": {
        "title": "Material Mood Pass",
        "domain": "materials",
        "intent": "Assign simple color/material language to a scene without complex shaders.",
        "estimated_minutes": 15,
        "steps": [
            "Choose three mood words for the scene.",
            "Create a small palette of 3 to 5 named materials.",
            "Apply materials to major objects only.",
            "Take one viewport screenshot or write a short palette note.",
            "List one material that should become more detailed later.",
        ],
        "success_checks": [
            "Materials are named by purpose or mood.",
            "No procedural shader complexity is added yet.",
            "The mood is legible from a quick viewport glance.",
        ],
    },
    "camera_render_preview": {
        "title": "Camera Render Preview",
        "domain": "render_pipeline",
        "intent": "Frame a scene and prepare a low-risk preview render plan.",
        "estimated_minutes": 15,
        "steps": [
            "Add or select one camera.",
            "Frame the subject with a simple composition: close, medium, or wide.",
            "Add one key light or use an existing light.",
            "Set a low preview resolution and low sample count.",
            "Write down the intended output filename before rendering.",
        ],
        "success_checks": [
            "Camera framing is intentional.",
            "Preview settings are lightweight.",
            "No final/high-cost render is launched by Pip.",
        ],
    },
    "safe_python_script_draft": {
        "title": "Safe Blender Python Script Draft",
        "domain": "python_automation",
        "intent": "Draft a Blender Python helper script for human review, not execution.",
        "estimated_minutes": 20,
        "steps": [
            "Describe the exact Blender action the script should automate.",
            "List the objects or collections it is allowed to touch.",
            "Draft the Python script into Pip memory only.",
            "Add comments for any operation that modifies scene data.",
            "Queue approval before running anything inside Blender.",
        ],
        "success_checks": [
            "Script is draft-only.",
            "Allowed scene targets are explicit.",
            "Execution requires a separate approval request.",
        ],
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def recipes_dir() -> Path:
    path = pip_config.get_memory_path() / "blender_recipes"
    path.mkdir(parents=True, exist_ok=True)
    return path


def index_path() -> Path:
    return recipes_dir() / "recipe_index.json"


def _read_index() -> dict[str, Any]:
    path = index_path()
    if not path.exists():
        return {"version": 1, "drafts": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {"version": 1, "drafts": []}
    data.setdefault("version", 1)
    data.setdefault("drafts", [])
    return data


def _write_index(data: dict[str, Any]) -> None:
    data["drafts"] = data.get("drafts", [])[-100:]
    index_path().write_text(json.dumps(data, indent=2), encoding="utf-8")


def list_recipes() -> dict[str, Any]:
    return {
        "recipes": [
            {"key": key, **value}
            for key, value in sorted(RECIPES.items(), key=lambda item: item[1]["title"])
        ],
        "history": _read_index().get("drafts", [])[-10:],
    }


def draft_recipe(recipe_key: str, project: str = "", goal: str = "") -> dict[str, Any]:
    if recipe_key not in RECIPES:
        raise ValueError(f"Unknown Blender recipe: {recipe_key}")

    recipe = RECIPES[recipe_key]
    created_at = utc_now()
    draft_id = hashlib.sha1(f"{recipe_key}:{project}:{goal}:{created_at}".encode("utf-8")).hexdigest()[:12]
    filename = f"{created_at[:10]}_{recipe_key}_{draft_id}.json"
    draft_path = recipes_dir() / filename
    draft = {
        "id": draft_id,
        "created_at": created_at,
        "status": "drafted",
        "app": "Blender",
        "recipe_key": recipe_key,
        "project": project or "Unassigned Blender practice",
        "goal": goal or recipe["intent"],
        "safety_mode": "draft_only",
        "requires_approval_before": [
            "opening Blender",
            "running Blender Python",
            "typing/clicking in Blender",
            "rendering expensive outputs",
            "editing production files",
        ],
        "recipe": recipe,
        "handoff_prompt": (
            f"Use this as a human-reviewed Blender plan. Do not execute actions automatically. "
            f"Recipe: {recipe['title']}. Goal: {goal or recipe['intent']}"
        ),
    }
    draft_path.write_text(json.dumps(draft, indent=2), encoding="utf-8")

    index = _read_index()
    index.setdefault("drafts", []).append(
        {
            "id": draft_id,
            "recipe_key": recipe_key,
            "title": recipe["title"],
            "domain": recipe["domain"],
            "project": draft["project"],
            "goal": draft["goal"],
            "status": "drafted",
            "created_at": created_at,
            "path": str(draft_path),
        }
    )
    _write_index(index)

    pip_app_skills.award_app_xp(
        "Blender",
        5,
        domain=recipe["domain"],
        evidence=f"Drafted safe recipe: {recipe['title']}",
    )
    return draft


def record_result(draft_id: str, status: str, note: str = "") -> dict[str, Any]:
    if status not in {"practiced", "completed", "deferred", "needs_revision"}:
        raise ValueError("status must be practiced, completed, deferred, or needs_revision")

    index = _read_index()
    match = None
    for item in index.get("drafts", []):
        if item.get("id") == draft_id:
            match = item
            break
    if not match:
        raise ValueError(f"Unknown Blender recipe draft id: {draft_id}")

    match["status"] = status
    match["result_note"] = note
    match["updated_at"] = utc_now()
    _write_index(index)

    xp = 20 if status == "completed" else 10 if status == "practiced" else 0
    if xp:
        pip_app_skills.award_app_xp(
            "Blender",
            xp,
            domain=match.get("domain", "general"),
            evidence=note or f"Marked recipe {status}: {match.get('title')}",
        )
    return match
