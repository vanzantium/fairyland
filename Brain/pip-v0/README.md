# Pip v0

Laptop prototype for the first Pip build sprint.

This prototype focuses on the real moat:

- ingest one week of phone usage events
- compress that behavior into friction patterns
- derive a small set of tattoos
- emit one proposal card

## Files

- `generate_synthetic_usage.py` - creates fake weekly phone telemetry
- `pip_engine.py` - compression pipeline and proposal logic
- `run_demo.py` - end-to-end demo runner
- `run_scenario_pack.py` - batch runner for named test scenarios
- `test_scenarios.py` - regression assertions for scenario behavior
- `pip_doctor.py` - project health check inspired by long-running agent tooling
- `pip_skills.py` - small local skill registry for repeatable Pip operations
- `pip_phone_bridge.py` - S25 usage import, validation, phone proposal, and feedback bridge
- `pip_workspace.py` - approved-folder work loop for draft-only project scanning
- `pip_control_panel.py` - local web dashboard for phone approval/control
- `approved_workspaces.json` - permission manifest for laptop-side Pip workspaces
- `HERMES_OPENMYTHOS_COMPARISON.md` - notes on what to borrow from Hermes and OpenMythos
- `DEPLOYMENT_OPTIONS.md` - local S25 versus laptop/chat deployment options
- `ANDROID_TELEMETRY_SCHEMA.md` - JSON bridge contract between S25 exports and Pip
- `memory.json` - persistent tattoo/scar/proposal memory created after the first run

## Usage

Generate synthetic data:

```powershell
python generate_synthetic_usage.py --scenario doomscroll_week --output sample_usage_week.json
```

Generate the full test pack:

```powershell
python generate_synthetic_usage.py --pack-dir scenarios
```

Run the prototype:

```powershell
python run_demo.py --input sample_usage_week.json --memory memory.json
```

Apply feedback, then rerun:

```powershell
python run_demo.py --input sample_usage_week.json --memory memory.json --feedback rejected
python run_demo.py --input sample_usage_week.json --memory memory.json --feedback accepted
python run_demo.py --input sample_usage_week.json --memory memory.json --feedback resolved
```

Run the whole scenario pack:

```powershell
python run_scenario_pack.py --scenarios scenarios --output scenario_results.json
```

Run scenario assertions:

```powershell
python test_scenarios.py --scenarios scenarios
```

Run project health checks:

```powershell
python pip_doctor.py
```

List and run local skills:

```powershell
python pip_skills.py list
python pip_skills.py run run_weekly_dream --input scenarios/doomscroll_week.json --memory memory.json --output dream_result.json
python pip_skills.py run inspect_memory --memory memory.json
python pip_skills.py run export_proposal_card --result dream_result.json --output proposal_card.json
python pip_skills.py run validate_android_usage --input imports/s25_usage_last_7_days.json
```

Run the S25 phone bridge:

```powershell
python pip_skills.py run import_phone_usage --input imports/s25_usage_last_7_days.json
python pip_skills.py run inspect_phone_status
python pip_skills.py run apply_phone_feedback --feedback deferred --note "Not ready to act yet."
```

Run the no-app manual S25 bridge:

```powershell
python pip_skills.py run import_phone_summary --input imports/manual_phone_summary_template.csv
python pip_skills.py run inspect_phone_status
```

Manual summary format:

```text
app_name, launches, total_minutes, notifications_received, notifications_dismissed_unread, battery_points
YouTube, 18, 240, 6, 3, 18
Chrome, 32, 160, 0, 0, 10
Messages, 45, 55, 60, 35, 3
```

Use rough numbers from S25 Digital Wellbeing, Samsung Battery usage, and notification memory. This is intentionally approximate; it lets Pip test the full bridge before we build a native Android collector.

Run the Garden Spiders draft-only workspace loop:

```powershell
python pip_skills.py run scan_workspace --workspace garden_spiders
python pip_skills.py run condense_workspace --workspace garden_spiders
python pip_skills.py run draft_next_actions --workspace garden_spiders
python pip_skills.py run export_control_status --workspace garden_spiders
```

Run one supervised ambient cycle:

```powershell
python pip_skills.py run run_ambient_cycle --workspace garden_spiders --wake-minutes 30 --context "Continue Garden Spiders draft-only ambient planning."
python pip_skills.py run queue_next_wake --workspace garden_spiders --wake-minutes 30 --context "Check Garden Spiders drafts again."
```

Check or test the permission queue:

```powershell
python pip_skills.py run classify_action_permission --action-type code_edit
python pip_skills.py run request_permission --workspace garden_spiders --action-type code_edit --title "Review a code edit" --rationale "Original project files require approval."
python pip_skills.py run resolve_permission --workspace garden_spiders --request-id REQUEST_ID --decision denied --note "Not yet."
```

Inspect supervised background jobs:

```powershell
python pip_skills.py run list_jobs
python pip_skills.py run stop_job --job-id JOB_ID
```

Inspect Pip's app skill assessment layer. Blender starts with a small animation-team curriculum so progress can be tracked by domain instead of only by generic app XP:

```powershell
python pip_skills.py run inspect_app_skills --app Blender
python pip_skills.py run award_app_skill_xp --app Blender --domain modeling --amount 10 --evidence "Built a simple mesh blockout."
```

Bootstrap Pip's starter developer shells for Codex, Claude Code, and Antigravity. These create app skill profiles, persona handoff JSON, and allowed-app entries, but UI handoff remains approval-gated:

```powershell
python pip_skills.py run bootstrap_developer_shells
python pip_skills.py run inspect_developer_shells
python pip_skills.py run inspect_developer_shells --shell codex
```

Draft safe Blender task recipes before any app control or Blender Python execution:

```powershell
python pip_skills.py run list_blender_recipes
python pip_skills.py run draft_blender_recipe --recipe simple_character_blockout --project "Garden Spiders" --goal "Block out a tiny spider friend."
python pip_skills.py run record_blender_recipe_result --draft-id DRAFT_ID --status completed --note "Finished a primitive blockout."
```

Inspect Pip's Token Governor and Signal Sieve bridge. This layer estimates
interaction cost, uses local Signal Sieve when available, and shifts Pip through
BUILD / AUDIT / DWELL / SHED modes so low-value or runaway work gets compressed,
deferred, or blocked before it burns the user's attention budget:

```powershell
python pip_skills.py run inspect_token_governor
python pip_skills.py run govern_interaction --intent autonomous_goal --content "Have Pip run all night on this idea."
python pip_skills.py run record_token_event --intent chat --estimated-tokens 300 --actual-tokens 180 --saved-tokens 120
```

Start the phone-friendly local control panel:

```powershell
python pip_control_panel.py --host 0.0.0.0 --port 8787
```

The server prints a laptop URL and a same-Wi-Fi phone URL. Pip remains draft-only: it reads only approved Garden Spiders paths and writes generated artifacts only under `C:\Users\taylo\Documents\brain\Garden Spiders\project\docs\pip-drafts`.
The dashboard can run scan, run ambient, schedule the next wake, import pasted S25 usage JSON, record phone/build proposal feedback, and approve or deny pending permission requests.

## Cross-Platform Notes

Pip's brain layer is designed to run on Windows, macOS, and Linux:

- control panel and phone browser dashboard
- approved-workspace draft loop
- Token Governor and local Signal Sieve bridge
- Blender recipe drafts and app skill profiles
- jobs, permission queue, and memory files

The fuller "body" layer is OS-dependent:

- Windows currently has the most complete support for foreground app tracking, global hotkeys, native toast notifications, and keyboard macro recording.
- macOS/Linux should run the brain/dashboard safely, while unsupported body features report as unavailable instead of crashing.
- Hardware and installed-app scanning now use best-effort platform adapters.

To move Pip to another machine, prefer environment variables instead of editing code:

```powershell
$env:PIP_BRAIN_ROOT="C:\path\to\brain"
$env:PIP_MEMORY_PATH="C:\path\to\pip memory"
python pip_skills.py run inspect_platform
```

On macOS/Linux the same idea is:

```bash
export PIP_BRAIN_ROOT="$HOME/brain"
export PIP_MEMORY_PATH="$HOME/brain/pip memory"
python pip_skills.py run inspect_platform
```

## Current Scope

Included:

- synthetic usage input
- session/friction aggregation
- CFT-style thermal state
- tattoo extraction
- one proposal output
- persistent tattoo/proposal memory across cycles
- ranked proposal candidates
- `fur` reaction memory for quick surface response
- `skin` shell memory for decaying bias
- `tattoo` memory for durable compressed recurrence
- explicit proposal outcomes: `accepted`, `rejected`, `deferred`, `resolved`
- compost path for stale or solved proposal signals
- named test scenarios: `balanced_week`, `doomscroll_week`, `notification_hell_week`, `battery_bleed_week`, `healthy_week`
- scenario assertions to catch ranking regressions
- adaptive proposal refinement with halting when the top candidate is clear
- doctor checks for project files, scenario JSON, and scenario assertions
- local skills for weekly runs, memory inspection, Android import, and proposal export
- Android usage validation for the hybrid S25-to-laptop bridge
- S25 usage import inbox and phone proposal card generation
- approved Garden Spiders workspace scanning
- draft-only project digest, next-action proposal, and control status exports
- local web control panel for S25 browser approval/rejection/defer feedback
- supervised ambient cycle state, transcripts, next-wake scheduling, and permission queue
- visible background job status/logs with cooperative stop requests
- app skill profiles with Blender domains for navigation, modeling, materials, animation, Python automation, and rendering
- starter developer shells for Codex, Claude Code, and Antigravity with permission-gated persona handoffs
- draft-only Blender recipe plans that bridge learning, review, and later approved execution
- Token Governor bridge for interaction budgeting, Signal Sieve pressure checks, and user-overuse nudges

Not included yet:

- Android telemetry
- native Android app
- overlay
- LLM wording polish
- ZeroTap or AccessibilityService app control
- hidden daemon scheduling

## Next Build Step

Use the Garden Spiders ambient loop to approve one narrow draft at a time. Once this manual cycle feels good, add a visible scheduler/runner and then phone telemetry or optional phone automation after the laptop-side safety loop is stable.
