# Pip Deployment Options

There are two realistic deployment shapes.

## Option A - Local On S25

Pip runs on the phone itself.

Best for:

- privacy
- local-first behavior
- battery / attention reduction
- eventual app-shaped product

Prototype path:

1. Android app exports usage stats.
2. Python engine runs through Termux.
3. Proposal card appears in a simple local UI or export file.
4. Later, port engine logic to Kotlin.

Pros:

- data stays on the phone
- no messaging bridge required
- matches Pip's philosophy best
- easier to reason about phone resource use

Cons:

- Android permissions are the hard part
- UI and packaging take real Android work
- background execution must be conservative

## Option B - Laptop Brain, Phone Chat Surface

Pip runs on the laptop or a server, and the phone talks to it through a messaging surface such as WhatsApp, Telegram, Signal, or a local web UI.

Best for:

- fast iteration
- richer compute
- chat-style control
- Hermes-style long-running agent workflows

Prototype path:

1. Phone exports usage JSON.
2. Laptop runs Pip.
3. Proposal card is sent back through a chat or browser surface.

Pros:

- easier to build immediately
- easier to debug
- can reuse desktop Python directly
- no Android app required at first

Cons:

- phone usage data leaves the phone unless manually controlled
- WhatsApp automation is more fragile than a local app or web UI
- does not directly measure Pip's own phone footprint
- weaker fit for the local-first product goal

## Recommendation

Use both, but in this order:

1. Laptop-first for engine development.
2. Manual S25 export into Pip JSON.
3. Termux on S25 for local proof.
4. Native Android app once the schema and scoring stabilize.

For messaging, prefer a simple local web UI or Telegram-style bot before WhatsApp.
WhatsApp can work as a control surface, but it is not the clean foundation for Pip's core.

## Updated Hybrid Recommendation

The first working hybrid shape is now:

1. Laptop runs Pip's approved workspace loop.
2. S25 opens the local web control panel on the same Wi-Fi.
3. Pip writes only to approved draft folders.
4. The phone approves, rejects, defers, or checks status.
5. Later, add Tailscale so the same phone control panel works away from home without cloud relay or port forwarding.

jcode reinforces this split: phone as a rich client, laptop as the tool/file/model server.
Space Agent reinforces the dashboard direction: the control surface should be modular and extensible, but generated UI/workflows should stay in approved layers.

## Clean Milestone

The first proper S25 milestone is:

- S25 collects usage stats
- Pip runs locally
- one proposal is generated
- feedback updates local memory

That is the version where Pip becomes real on the phone.

The first proper hybrid milestone is already closer:

- laptop scans Garden Spiders
- Pip drafts next actions under `docs/pip-drafts`
- S25 controls the loop through the local dashboard
- feedback updates draft memory
- no original files or external apps are modified automatically
