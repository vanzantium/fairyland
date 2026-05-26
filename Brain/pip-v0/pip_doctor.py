#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path


REQUIRED_FILES = [
    "pip_engine.py",
    "generate_synthetic_usage.py",
    "run_demo.py",
    "run_scenario_pack.py",
    "test_scenarios.py",
    "pip_skills.py",
    "pip_phone_bridge.py",
    "pip_workspace.py",
    "pip_control_panel.py",
    "pip_safety.py",
    "pip_jobs.py",
    "pip_app_skills.py",
    "pip_blender_recipes.py",
    "pip_token_guard.py",
    "pip_platform.py",
    "pip_goal_engine.py",
    "pip_pc_bridge.py",
    "pip_pc_tracker.py",
    "pip_hardware_scanner.py",
    "pip_fairy_window.py",
    "approved_workspaces.json",
    "README.md",
    "S25_ROADMAP.md",
    "DEPLOYMENT_OPTIONS.md",
    "ANDROID_TELEMETRY_SCHEMA.md",
    "HERMES_OPENMYTHOS_COMPARISON.md",
]


def check_json(path: Path) -> tuple[bool, str]:
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, str(exc)
    return True, "ok"


def main() -> None:
    parser = argparse.ArgumentParser(description="Check Pip v0 project health.")
    parser.add_argument("--root", default=".", help="Pip v0 project root")
    parser.add_argument("--scenarios", default="scenarios", help="Scenario directory relative to root")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    failures: list[str] = []

    for filename in REQUIRED_FILES:
        if not (root / filename).exists():
            failures.append(f"missing required file: {filename}")

    with tempfile.TemporaryDirectory() as compile_cache:
        compile_cache_path = Path(compile_cache)
        for path in root.glob("*.py"):
            try:
                py_compile.compile(
                    str(path),
                    cfile=str(compile_cache_path / f"{path.stem}.pyc"),
                    doraise=True,
                )
            except py_compile.PyCompileError as exc:
                failures.append(f"python compile failed for {path.name}: {exc.msg}")
            except OSError as exc:
                failures.append(f"python compile failed for {path.name}: {exc}")

    scenario_dir = root / args.scenarios
    if scenario_dir.exists():
        scenario_files = [
            path for path in scenario_dir.glob("*.json")
            if path.name != "manifest.json" and not path.name.endswith(".memory.json")
        ]
        if not scenario_files:
            failures.append("scenario directory exists but contains no scenario JSON files")
        for path in scenario_files:
            ok, message = check_json(path)
            if not ok:
                failures.append(f"invalid JSON in {path.name}: {message}")
    else:
        failures.append(f"missing scenario directory: {args.scenarios}")

    test_script = root / "test_scenarios.py"
    if test_script.exists() and scenario_dir.exists():
        result = subprocess.run(
            [sys.executable, str(test_script), "--scenarios", str(scenario_dir)],
            cwd=str(root),
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            output = (result.stdout + result.stderr).strip()
            failures.append(f"scenario assertions failed: {output}")

    try:
        sys.path.insert(0, str(root))
        from pip_workspace import classify_action_permission

        for action_type in [
            "autonomous_goal",
            "arbitrary_python",
            "ui_automation",
            "keyboard_recording",
            "system_optimization",
        ]:
            classification = classify_action_permission(action_type)
            if classification.get("tier") != "requires_permission":
                failures.append(f"{action_type} should require permission")
    except Exception as exc:
        failures.append(f"permission policy check failed: {exc}")

    try:
        control_source = (root / "pip_control_panel.py").read_text(encoding="utf-8")
        if control_source.count('elif parsed.path == "/save-apps"') != 1:
            failures.append("dashboard should define exactly one /save-apps POST route")
        if 'Path("PipMemory") / "apps.json"' in control_source:
            failures.append("dashboard should use configured memory path, not hard-coded PipMemory/apps.json")
        if 'creationflags=0x08000000' in control_source:
            failures.append("dashboard should use pip_platform.hidden_subprocess_kwargs for hidden Windows processes")
    except Exception as exc:
        failures.append(f"dashboard source consistency check failed: {exc}")

    try:
        import pip_platform
        platform_status = pip_platform.feature_status()
        required_feature_keys = {"control_panel", "token_governor", "hardware_scan", "installed_app_scan"}
        missing = required_feature_keys.difference(platform_status.get("features", {}))
        if missing:
            failures.append(f"platform feature status missing keys: {sorted(missing)}")
    except Exception as exc:
        failures.append(f"platform compatibility check failed: {exc}")

    try:
        import pip_app_skills
        shells = pip_app_skills.inspect_developer_shells().get("shells", [])
        shell_names = {shell.get("name") for shell in shells}
        expected_shells = {"Codex", "Claude Code", "Antigravity"}
        missing_shells = expected_shells.difference(shell_names)
        if missing_shells:
            failures.append(f"developer shell registry missing: {sorted(missing_shells)}")
        for shell in shells:
            if shell.get("name") in expected_shells and shell.get("safety_mode") != "approval_required_for_ui_handoff":
                failures.append(f"{shell.get('name')} shell should be UI-handoff approval gated")
    except Exception as exc:
        failures.append(f"developer shell consistency check failed: {exc}")

    try:
        import pip_config
        import pip_token_guard
        import pip_jobs

        original_memory_path = pip_config.get_memory_path
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            pip_config.get_memory_path = lambda: temp_root
            status = pip_token_guard.record_event(
                "blocked_doctor",
                estimated_tokens=1000,
                actual_tokens=0,
                saved_tokens=1000,
                note="doctor blocked-accounting check",
            )
            if status["daily_used_tokens"] != 0 or status["daily_saved_tokens"] != 1000:
                failures.append("blocked token-governor events should save tokens without spending them")
            if pip_jobs.request_stop("missing-job").get("ok"):
                failures.append("stopping an unknown job should not succeed")
            if (temp_root / "jobs" / "missing-job.stop").exists():
                failures.append("stopping an unknown job should not create an orphan stop file")
        pip_config.get_memory_path = original_memory_path
    except Exception as exc:
        failures.append(f"token governor/job consistency check failed: {exc}")
    finally:
        try:
            pip_config.get_memory_path = original_memory_path
        except Exception:
            pass

    if failures:
        print("Pip doctor found issues:")
        for failure in failures:
            print(f"- {failure}")
        raise SystemExit(1)

    print("Pip doctor passed.")


if __name__ == "__main__":
    main()
