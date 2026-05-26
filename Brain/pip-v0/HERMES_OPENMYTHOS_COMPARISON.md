# External Agent Comparison For Pip

This note compares Pip v0 against Hermes Agent, OpenMythos, jcode, and Space Agent, then identifies the parts worth adapting.

## Current Pip Shape

Pip is a local phone-friction compression engine:

- ingest usage events
- compress them into tattoos
- rank proposal candidates
- emit one proposal
- learn from feedback through fur, skin, tattoo, cooldown, and compost memory

Pip's product constraint is still: reduce attention demand and device load.

## Hermes Agent

Hermes is most relevant as an operations model.

Useful pieces:

- long-running identity across sessions
- persistent memory
- command and tool configuration
- doctor / health checks
- scheduled work
- skills as reusable procedures
- multi-surface access
- explicit security and approval boundaries

What Pip should borrow:

- `pip_doctor.py` style health checks
- scheduled low-impact dream cycles
- explicit tool / permission registry before Android features expand
- reusable skills for data import, proposal export, and memory inspection

What Pip should avoid for now:

- broad chat-agent behavior
- always-on task execution
- too many tools before the core proposal engine is reliable

## OpenMythos

OpenMythos is most relevant as a reasoning-control model, not as something to embed directly.

Useful pieces:

- prelude -> recurrent block -> coda pipeline
- adaptive compute / halting
- recurrent depth for harder inputs
- expert routing for different problem types
- stable input injection so loops do not drift away from original signal

What Pip should borrow:

- an adaptive proposal refinement loop
- halting when the top proposal is already clear
- small expert nudges for notification, battery, and attention-drain candidates
- preserving raw telemetry as an invariant while memory biases the decision

What Pip should avoid for now:

- training a custom transformer
- GPU-heavy dependencies
- making Pip's first phone version depend on LLM inference

## jcode

jcode is most relevant as a laptop agent harness and phone-control reference.

Useful pieces:

- persistent server/client shape for multiple sessions
- ambient background mode for memory gardening, scouting, and small proactive work
- graph-like memory with semantic retrieval, consolidation, contradiction handling, and provenance
- safety tiers for unmonitored work
- phone client direction where the phone is a touch control surface and the laptop/server does file, shell, git, MCP, and model work
- Tailscale-first remote access pattern for phone-to-laptop control beyond same-Wi-Fi
- side panels, info widgets, and status surfaces that keep long-running agent work legible
- swarm/session coordination, including notifying agents when files change under them

What Pip should borrow:

- ambient cycle shape: scan -> garden memory -> scout opportunities -> draft supervised work -> summarize
- a persistent queue for proposed work, next wake, feedback, and approval state
- explicit action classification before any agent can edit code, send messages, open ports broadly, or automate apps
- phone dashboard status fields: running, paused, last cycle, next cycle, latest proposal, pending approval, budget/limits
- future Tailscale option after the LAN dashboard is stable
- memory provenance fields so Pip can explain why a compressed idea or task exists

What Pip should avoid for now:

- autonomous code edits outside a draft folder
- multi-agent swarms before single-agent safety is boring and reliable
- provider/account complexity before the local control loop proves useful
- self-modifying Pip behavior without a review branch and approval queue

## Space Agent

Space Agent is most relevant as an interface/workspace model.

Useful pieces:

- browser-first agent that can reshape the running workspace interface
- thin Node server plus frontend runtime
- skills as simple text files that can be added or extended
- modular customware layers rather than one rigid app surface
- per-user and group layers for shared tools/workflows later
- Git-backed local history and admin/time-travel recovery

What Pip should borrow:

- make the control panel extensible instead of hardcoding every future view
- treat Pip skills as editable, inspectable capability cards
- add a stable admin/recovery view before allowing more automation
- keep generated tools/workflows in a separate writable layer, analogous to Pip's `docs/pip-drafts`
- eventually let Pip generate small dashboard widgets for a project, but only in its approved draft/control layer first

What Pip should avoid for now:

- letting the agent reshape the whole UI/runtime without permissions
- server/user/group complexity before Pip has one reliable personal workflow
- using browser-runtime power as a substitute for file/folder permission boundaries

## Already Added

- `pip_doctor.py` for Hermes-style project health checks
- adaptive refinement loop in `pip_engine.py`
- `decision_trace` output showing loop count, halt reason, and margin
- `pip_skills.py` as a small local skill registry
- `approved_workspaces.json` for draft-only folder boundaries
- `pip_workspace.py` for approved workspace scanning, condensation, next-action drafts, and control status
- `pip_control_panel.py` as the first phone-friendly local dashboard

## Next Good Borrow

Expand the work loop with jcode-style ambient structure and Space-style control widgets without expanding permissions.

Near-term candidates:

- `run_ambient_cycle`
- `inspect_workspace_memory`
- `queue_next_wake`
- `classify_action_permission`
- `render_dashboard_widget`
- `validate_android_export`

## S25 Implication

Hermes suggests Pip needs operational durability.
OpenMythos suggests Pip needs bounded depth.
jcode suggests the phone should first be a trusted control surface for a laptop/server brain.
Space Agent suggests Pip's dashboard should become a living workspace, but only through approved layers.

Together, that means the S25 version should not be a chat app first and should not start with broad phone automation.
It should begin as a quiet control panel for a local laptop loop, then graduate to Tailscale/remote access, Android telemetry, and eventually approved app-control hands.
