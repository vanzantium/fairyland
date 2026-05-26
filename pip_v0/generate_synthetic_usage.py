#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from datetime import datetime, timedelta, timezone


BASE_APP_PROFILES = {
    "TikTok": {"sessions": (5, 11), "duration_s": (8, 45), "battery": (1, 3), "notifications": (2, 8)},
    "YouTube": {"sessions": (2, 5), "duration_s": (180, 1400), "battery": (2, 6), "notifications": (0, 2)},
    "Messages": {"sessions": (6, 14), "duration_s": (12, 120), "battery": (0, 1), "notifications": (4, 10)},
    "Chrome": {"sessions": (4, 9), "duration_s": (30, 300), "battery": (1, 3), "notifications": (0, 1)},
    "Spotify": {"sessions": (1, 3), "duration_s": (900, 3600), "battery": (1, 4), "notifications": (0, 1)},
    "Gmail": {"sessions": (2, 6), "duration_s": (20, 120), "battery": (0, 2), "notifications": (1, 5)},
    "Maps": {"sessions": (0, 2), "duration_s": (120, 1800), "battery": (2, 5), "notifications": (0, 0)},
    "Calendar": {"sessions": (0, 2), "duration_s": (15, 80), "battery": (0, 1), "notifications": (0, 1)},
}


SCENARIOS = {
    "balanced_week": {
        "description": "Mixed normal usage with one mild noisy app.",
        "overrides": {},
        "removals": [],
    },
    "doomscroll_week": {
        "description": "Heavy short-session scrolling with high launch counts.",
        "overrides": {
            "TikTok": {"sessions": (10, 18), "duration_s": (7, 28), "battery": (2, 4), "notifications": (3, 9)},
            "YouTube": {"sessions": (6, 10), "duration_s": (20, 90), "battery": (2, 5), "notifications": (1, 4)},
            "Chrome": {"sessions": (8, 14), "duration_s": (15, 70), "battery": (1, 3), "notifications": (0, 1)},
        },
        "removals": [],
    },
    "notification_hell_week": {
        "description": "Interrupt-heavy week with lots of ignored notifications.",
        "overrides": {
            "TikTok": {"sessions": (0, 2), "duration_s": (8, 20), "battery": (1, 2), "notifications": (0, 1)},
            "Messages": {
                "sessions": (12, 18),
                "duration_s": (45, 100),
                "battery": (0, 1),
                "notifications": (10, 18),
                "dismiss_ratio": (0.75, 1.0),
            },
            "Gmail": {
                "sessions": (8, 14),
                "duration_s": (40, 100),
                "battery": (0, 1),
                "notifications": (8, 16),
                "dismiss_ratio": (0.75, 1.0),
            },
            "Calendar": {
                "sessions": (3, 5),
                "duration_s": (20, 60),
                "battery": (0, 1),
                "notifications": (6, 10),
                "dismiss_ratio": (0.8, 1.0),
            },
        },
        "removals": [],
    },
    "battery_bleed_week": {
        "description": "Apps burning battery in short or fragmented sessions.",
        "overrides": {
            "TikTok": {"sessions": (2, 4), "duration_s": (15, 40), "battery": (4, 7), "notifications": (0, 2)},
            "Messages": {"sessions": (10, 16), "duration_s": (35, 80), "battery": (3, 5), "notifications": (4, 8)},
            "Maps": {"sessions": (3, 5), "duration_s": (120, 300), "battery": (6, 9), "notifications": (0, 0)},
            "Chrome": {"sessions": (6, 10), "duration_s": (40, 110), "battery": (3, 5), "notifications": (0, 1)},
        },
        "removals": [],
    },
    "healthy_week": {
        "description": "Lower-noise week with longer useful sessions and fewer interruptions.",
        "overrides": {
            "TikTok": {"sessions": (0, 2), "duration_s": (10, 25), "battery": (1, 2), "notifications": (0, 1)},
            "YouTube": {"sessions": (1, 3), "duration_s": (600, 1800), "battery": (2, 5), "notifications": (0, 1)},
            "Messages": {"sessions": (4, 8), "duration_s": (20, 90), "battery": (0, 1), "notifications": (2, 5)},
            "Chrome": {"sessions": (2, 5), "duration_s": (120, 420), "battery": (1, 3), "notifications": (0, 0)},
            "Spotify": {"sessions": (1, 2), "duration_s": (1800, 5400), "battery": (1, 3), "notifications": (0, 0)},
            "Gmail": {"sessions": (1, 3), "duration_s": (40, 120), "battery": (0, 1), "notifications": (1, 3)},
            "Maps": {"sessions": (0, 1), "duration_s": (120, 900), "battery": (2, 4), "notifications": (0, 0)},
            "Calendar": {"sessions": (1, 2), "duration_s": (20, 70), "battery": (0, 1), "notifications": (0, 1)},
        },
        "removals": [],
    },
}


def random_event_time(day_start: datetime) -> datetime:
    hour = random.randint(7, 23)
    minute = random.randint(0, 59)
    second = random.randint(0, 59)
    return day_start.replace(hour=hour, minute=minute, second=second)


def build_profiles(scenario_name: str) -> dict[str, dict]:
    scenario = SCENARIOS[scenario_name]
    profiles = {
        app_name: dict(values)
        for app_name, values in BASE_APP_PROFILES.items()
    }
    for app_name, override in scenario["overrides"].items():
        profiles[app_name] = dict(override)
    for app_name in scenario.get("removals", []):
        profiles.pop(app_name, None)
    return profiles


def build_week(seed: int, scenario_name: str) -> list[dict]:
    random.seed(seed)
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
    events: list[dict] = []
    profiles = build_profiles(scenario_name)

    for day_index in range(7):
        day_start = start + timedelta(days=day_index)
        for app_name, profile in profiles.items():
            min_sessions, max_sessions = profile["sessions"]
            session_count = random.randint(min_sessions, max_sessions)
            for _ in range(session_count):
                launch_time = random_event_time(day_start)
                duration = random.randint(*profile["duration_s"])
                battery_delta = random.randint(*profile["battery"])
                notifications = random.randint(*profile["notifications"])
                if notifications and "dismiss_ratio" in profile:
                    ratio = random.uniform(*profile["dismiss_ratio"])
                    dismissed_unread = min(notifications, round(notifications * ratio))
                else:
                    dismissed_unread = random.randint(0, notifications) if notifications else 0

                events.append(
                    {
                        "timestamp": launch_time.isoformat(),
                        "app_name": app_name,
                        "event_type": "launch",
                        "battery_delta": battery_delta,
                        "notifications_received": notifications,
                        "notifications_dismissed_unread": dismissed_unread,
                        "session_duration_seconds": duration,
                    }
                )

    events.sort(key=lambda item: item["timestamp"])
    return events


def write_scenario_pack(output_dir: str, seed: int) -> None:
    base = Path(output_dir)
    base.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict] = {}
    for index, scenario_name in enumerate(SCENARIOS):
        scenario_seed = seed + index
        events = build_week(scenario_seed, scenario_name)
        file_path = base / f"{scenario_name}.json"
        with open(file_path, "w", encoding="utf-8") as handle:
            json.dump(events, handle, indent=2)
        manifest[scenario_name] = {
            "file": file_path.name,
            "seed": scenario_seed,
            "description": SCENARIOS[scenario_name]["description"],
            "event_count": len(events),
        }

    with open(base / "manifest.json", "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)

    print(f"Wrote {len(manifest)} scenarios to {base}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic one-week phone usage data for Pip v0.")
    parser.add_argument("--output", default="sample_usage_week.json", help="Output JSON file path")
    parser.add_argument("--seed", type=int, default=109, help="Random seed")
    parser.add_argument(
        "--scenario",
        choices=sorted(SCENARIOS.keys()),
        default="balanced_week",
        help="Named scenario to generate",
    )
    parser.add_argument(
        "--pack-dir",
        help="If set, generate the full named scenario pack into this directory instead of one file",
    )
    args = parser.parse_args()

    if args.pack_dir:
        write_scenario_pack(args.pack_dir, args.seed)
        return

    events = build_week(args.seed, args.scenario)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(events, handle, indent=2)

    print(f"Wrote {len(events)} events to {args.output} ({args.scenario})")


if __name__ == "__main__":
    main()
