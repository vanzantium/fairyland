#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path

from generate_synthetic_usage import write_scenario_pack
from pip_engine import PipEngine


SCENARIO_EXPECTATIONS = {
    "balanced_week": {
        "kinds": {"attention_drain", "battery_mismatch"},
        "min_score": 0.45,
    },
    "doomscroll_week": {
        "kinds": {"attention_drain"},
        "min_score": 0.75,
    },
    "notification_hell_week": {
        "kinds": {"notification_drag"},
        "min_score": 0.65,
    },
    "battery_bleed_week": {
        "kinds": {"battery_mismatch"},
        "min_score": 0.65,
    },
    "healthy_week": {
        "kinds": {"none"},
        "max_score": 0.0,
    },
}


def run_assertions(scenario_dir: Path) -> list[str]:
    failures: list[str] = []

    for scenario_name, expectation in SCENARIO_EXPECTATIONS.items():
        scenario_file = scenario_dir / f"{scenario_name}.json"
        if not scenario_file.exists():
            failures.append(f"{scenario_name}: missing scenario file")
            continue

        memory_path = scenario_dir / f"{scenario_name}.assert.memory.json"
        if memory_path.exists():
            memory_path.unlink()

        engine = PipEngine(memory_path=str(memory_path))
        result = engine.run(str(scenario_file))
        proposal = result["proposal_card"]
        source_kind = proposal["source_kind"]
        score = proposal["score"]

        expected_kinds = expectation["kinds"]
        if source_kind not in expected_kinds:
            failures.append(
                f"{scenario_name}: expected kind in {sorted(expected_kinds)}, got {source_kind!r}"
            )

        min_score = expectation.get("min_score")
        if min_score is not None and score < min_score:
            failures.append(
                f"{scenario_name}: expected score >= {min_score}, got {score}"
            )

        max_score = expectation.get("max_score")
        if max_score is not None and score > max_score:
            failures.append(
                f"{scenario_name}: expected score <= {max_score}, got {score}"
            )

    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description="Assert Pip v0 behavior against named scenario fixtures.")
    parser.add_argument("--scenarios", help="Existing scenario directory to test")
    parser.add_argument("--seed", type=int, default=109, help="Seed used when generating temporary scenarios")
    args = parser.parse_args()

    temp_dir: str | None = None
    if args.scenarios:
        scenario_dir = Path(args.scenarios)
    else:
        temp_dir = tempfile.mkdtemp(prefix="pip-v0-scenarios-")
        scenario_dir = Path(temp_dir)
        write_scenario_pack(str(scenario_dir), args.seed)

    try:
        failures = run_assertions(scenario_dir)
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)

    if failures:
        print("Scenario assertions failed:")
        for failure in failures:
            print(f"- {failure}")
        raise SystemExit(1)

    print("Scenario assertions passed.")


if __name__ == "__main__":
    main()
