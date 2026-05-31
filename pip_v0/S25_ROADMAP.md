# Pip on S25 Roadmap

This is the practical path from the current laptop prototype to a real S25 app or on-device system.

## Current State

Pip v0 already has:

- a working compression engine
- persistent memory
- fur / skin / tattoo memory tiers
- feedback outcomes
- scenario fixtures
- regression assertions

This is enough to begin Android input design.

## Target Shape

The S25 build should become three separable pieces:

1. Android collector
2. Pip engine
3. Approval UI

The overlay / Proto Pip body is a later layer after the product core works with real telemetry.

There is now also a laptop-hybrid path:

1. Laptop worker
2. S25 control panel
3. Approved draft folders
4. Later remote access through Tailscale or a native app

This is the fastest way to get Pip working with real projects before the Android collector exists.

## Phase 1 - Android Telemetry App

Goal:
Collect real phone usage events and export them into the same JSON shape the laptop engine already understands.

Likely Android APIs:

- `UsageStatsManager` for app usage windows and aggregate app stats
- local SQLite or JSON file export for event history
- manual permission screen for Usage Access

Deliverable:

- S25 app with one button: export last 7 days
- exported JSON matches Pip v0 input schema
- laptop Pip can read the exported file without code changes

This is the first real bridge.

## Phase 0 - Laptop Hybrid Control

Goal:
Use the S25 as a safe controller while the laptop does the heavy work.

Current deliverable:

- approved Garden Spiders workspace
- draft-only outputs under `docs/pip-drafts`
- local web control panel for scan / approve / reject / defer / memory

Next deliverable:

- scheduled ambient cycle with visible next wake time
- action-permission classifier before any code edits or app automation
- optional Tailscale access once the LAN dashboard is stable

## Phase 2 - On-Device Engine

Goal:
Run Pip's compression engine on the phone.

Two viable paths:

- bundle a native Android/Kotlin port of the engine
- run Python through Termux during prototype phase

Recommended order:

1. Keep Python engine for speed while testing.
2. Once the scoring stabilizes, port the core logic to Kotlin.

Deliverable:

- S25 generates a proposal from its own telemetry
- no cloud dependency
- memory persists locally

## Phase 3 - Approval UI

Goal:
Build the trust surface.

Minimum UI:

- one proposal card
- evidence text
- approve / reject / defer / resolved buttons
- current thermal state
- memory inspection screen

Deliverable:

- user can accept or reject a proposal
- feedback updates memory
- next run changes behavior accordingly

## Phase 4 - Scheduled Dream Cycle

Goal:
Run Pip at low-impact times.

Use Android background scheduling with constraints:

- charging
- battery not low
- ideally idle
- local-only processing

Deliverable:

- Pip runs a weekly or nightly compression pass
- proposal is ready when the user opens the app
- no constant background drain

## Phase 5 - Proto Pip Body

Goal:
Add the visual layer after the core is useful.

Possible components:

- overlay permission for a floating sprite
- state file or local database read for thermal changes
- optional accessibility service only if it becomes a real assistive workflow

Important boundary:
Accessibility should not be required for v1. It is powerful, permission-heavy, and trust-sensitive.

## Minimal Real App Milestone

The first version worth installing on the S25 is:

- collects usage stats
- runs local proposal generation
- shows one proposal
- accepts feedback
- persists memory

No overlay.
No accessibility.
No clipboard routing.
No cloud.

That is the cleanest app-shaped Pip.

## Approximate Build Distance

From current state:

- engine core: mostly started
- test harness: started
- Android telemetry bridge: not started
- Android UI: not started
- background scheduling: not started
- overlay body: later

The next coding target should be the Android telemetry schema and an export adapter.

## Next File To Create

`ANDROID_TELEMETRY_SCHEMA.md` is now the bridge contract.

Next implementation target:

- build a tiny Android usage exporter
- export last 7 days into the normalized schema
- validate it with `pip_skills.py`
- run the weekly dream locally on laptop first, then Termux
