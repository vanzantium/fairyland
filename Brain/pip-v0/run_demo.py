#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from pip_engine import PipEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Pip v0 laptop prototype.")
    parser.add_argument("--input", required=True, help="Path to usage JSON input")
    parser.add_argument("--output", help="Optional path to write JSON result")
    parser.add_argument("--memory", default="memory.json", help="Path to persistent Pip memory JSON")
    parser.add_argument(
        "--feedback",
        choices=["accepted", "rejected", "deferred", "resolved"],
        help="Apply feedback to the previous proposal before running",
    )
    args = parser.parse_args()

    engine = PipEngine(memory_path=args.memory)
    result = engine.run(args.input, feedback=args.feedback)

    print("\nPip v0 Proposal")
    print("----------------")
    print(result["proposal_card"]["proposal"])
    print(result["proposal_card"]["evidence"])
    print(f"Score: {result['proposal_card']['score']} ({result['proposal_card']['source_kind']})")
    print("\nThermal State")
    print(json.dumps(result["thermal_state"], indent=2))
    print("\nMemory")
    print(json.dumps(result["memory"], indent=2))

    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2)
        print(f"\nWrote result to {args.output}")


if __name__ == "__main__":
    main()
