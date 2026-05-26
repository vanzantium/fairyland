#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pip_engine import PipEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Pip v0 across a directory of scenario JSON files.")
    parser.add_argument("--scenarios", required=True, help="Directory containing scenario JSON files")
    parser.add_argument("--output", default="scenario_results.json", help="Output JSON summary path")
    args = parser.parse_args()

    scenario_dir = Path(args.scenarios)
    scenario_files = sorted(
        path for path in scenario_dir.glob("*.json")
        if path.name != "manifest.json" and not path.name.endswith(".memory.json")
    )

    summary: dict[str, dict] = {}
    for scenario_file in scenario_files:
        memory_path = scenario_dir / f"{scenario_file.stem}.memory.json"
        if memory_path.exists():
            memory_path.unlink()

        engine = PipEngine(memory_path=str(memory_path))
        result = engine.run(str(scenario_file))
        summary[scenario_file.stem] = {
            "proposal": result["proposal_card"],
            "thermal_state": result["thermal_state"],
            "decision_trace": result["decision_trace"],
            "top_candidates": result["proposal_candidates"][:3],
        }

    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)

    print(f"Wrote scenario summary for {len(summary)} scenarios to {args.output}")


if __name__ == "__main__":
    main()
