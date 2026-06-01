# Android Telemetry Schema

This is the bridge between the S25 collector and the current Pip engine.

The hybrid approach is:

1. S25 collects or exports usage data.
2. Laptop Pip validates the export.
3. Laptop Pip runs the weekly dream.
4. Later, the same validated schema runs directly on S25 through Termux or a native Android port.

## Normalized Pip Event

The current Pip engine expects a JSON array of event objects.

Required fields:

| Field | Type | Example | Notes |
|---|---|---|---|
| `timestamp` | string | `2026-04-27T13:45:00-07:00` | ISO-8601 timestamp |
| `app_name` | string | `Messages` | Human-readable app label |
| `event_type` | string | `launch` | Start with `launch`; later allow `foreground`, `background`, `close` |
| `battery_delta` | integer | `2` | Relative battery cost estimate for the session |
| `notifications_received` | integer | `12` | Notifications attributed to this app during the session/window |
| `notifications_dismissed_unread` | integer | `9` | Notifications dismissed or cleared without opening |
| `session_duration_seconds` | integer | `42` | Session length in seconds |

Example:

```json
[
  {
    "timestamp": "2026-04-27T13:45:00-07:00",
    "app_name": "Messages",
    "event_type": "launch",
    "battery_delta": 1,
    "notifications_received": 8,
    "notifications_dismissed_unread": 6,
    "session_duration_seconds": 55
  }
]
```

## Android Raw Sources

Phase 1 should use the least invasive sources.

Likely raw sources:

- `UsageStatsManager` for app foreground windows and aggregate usage
- app label lookup through package metadata
- optional manual battery estimate if per-app battery is not available in the export
- optional notification listener later, not required for the first bridge

## Permission Notes

Usage stats require the user to manually grant Usage Access.

The first bridge should not require:

- Accessibility Service
- overlay permission
- notification listener
- contacts
- SMS
- microphone
- location

Notification counts can stay synthetic, zero, or manually estimated until the collector is ready for a Notification Listener.

## Validation Rules

An Android export is accepted when:

- the root value is a JSON array
- every item is an object
- all required fields exist
- numeric fields are integers >= 0
- `notifications_dismissed_unread <= notifications_received`
- `session_duration_seconds > 0`
- `timestamp` is present and non-empty
- `app_name` is present and non-empty

The validator should warn, not fail, when:

- `event_type` is not `launch`
- `battery_delta` is always zero
- notification fields are always zero

## File Naming

Suggested export names:

- `s25_usage_YYYY-MM-DD.json`
- `s25_usage_last_7_days.json`
- `pip_android_export.json`

Suggested local paths:

- laptop input: `imports/s25_usage_last_7_days.json`
- phone export: `Download/Pip/s25_usage_last_7_days.json`

## First Bridge Milestone

The first S25 bridge is successful when:

1. The phone produces a JSON file matching this schema.
2. `python pip_skills.py run validate_android_usage --input imports/s25_usage_last_7_days.json` passes.
3. `python pip_skills.py run run_weekly_dream --input imports/s25_usage_last_7_days.json --memory memory.json --output latest_dream.json` produces one proposal.

At that point, Pip has crossed from synthetic data into real phone data.
