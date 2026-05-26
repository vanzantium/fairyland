#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from statistics import mean
from typing import Any


SHORT_SESSION_SECONDS = 30
LOW_SIGNAL_SESSION_SECONDS = 45
MAX_REFINEMENT_LOOPS = 3
HALT_MARGIN = 0.12


@dataclass
class UsageEvent:
    timestamp: str
    app_name: str
    event_type: str
    battery_delta: int
    notifications_received: int
    notifications_dismissed_unread: int
    session_duration_seconds: int


@dataclass
class AppAggregate:
    app_name: str
    launches: int = 0
    total_duration_seconds: int = 0
    short_sessions: int = 0
    low_signal_sessions: int = 0
    battery_delta_total: int = 0
    notifications_received: int = 0
    notifications_dismissed_unread: int = 0

    @property
    def average_duration_seconds(self) -> float:
        return self.total_duration_seconds / self.launches if self.launches else 0.0

    @property
    def short_session_ratio(self) -> float:
        return self.short_sessions / self.launches if self.launches else 0.0

    @property
    def low_signal_ratio(self) -> float:
        return self.low_signal_sessions / self.launches if self.launches else 0.0

    @property
    def unread_dismiss_ratio(self) -> float:
        if self.notifications_received == 0:
            return 0.0
        return self.notifications_dismissed_unread / self.notifications_received


@dataclass
class ThermalState:
    coherence: float
    pressure: float
    drift: float
    groove: float
    integration_debt: float
    scar: float


@dataclass
class Tattoo:
    kind: str
    app_name: str
    summary: str
    confidence: float
    recurrence: int = 1


@dataclass
class ProposalCard:
    proposal: str
    evidence: str
    rationale_tags: list[str]
    score: float
    source_kind: str


@dataclass
class ProposalCandidate:
    kind: str
    app_name: str
    score: float
    evidence: str
    rationale_tags: list[str]
    proposal: str


@dataclass
class DecisionTrace:
    loops_run: int
    halted_reason: str
    top_margin: float
    notes: list[str] = field(default_factory=list)


@dataclass
class MemoryState:
    cycle_count: int = 0
    tattoo_history: dict[str, int] = field(default_factory=dict)
    skin_weights: dict[str, float] = field(default_factory=dict)
    fur_reactions: list[dict[str, Any]] = field(default_factory=list)
    cooldowns: dict[str, float] = field(default_factory=dict)
    compost_log: list[dict[str, Any]] = field(default_factory=list)
    proposal_history: list[dict[str, Any]] = field(default_factory=list)


class PipEngine:
    def __init__(self, memory_path: str | None = None):
        self.memory_path = Path(memory_path) if memory_path else None

    def load_events(self, input_path: str) -> list[UsageEvent]:
        with open(input_path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        return [UsageEvent(**item) for item in raw]

    def load_memory(self) -> MemoryState:
        if not self.memory_path or not self.memory_path.exists():
            return MemoryState()
        with open(self.memory_path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        return MemoryState(
            cycle_count=raw.get("cycle_count", 0),
            tattoo_history=raw.get("tattoo_history", {}),
            skin_weights=raw.get("skin_weights", {}),
            fur_reactions=raw.get("fur_reactions", []),
            cooldowns=raw.get("cooldowns", {}),
            compost_log=raw.get("compost_log", []),
            proposal_history=raw.get("proposal_history", []),
        )

    def save_memory(self, memory: MemoryState) -> None:
        if not self.memory_path:
            return
        self.memory_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.memory_path, "w", encoding="utf-8") as handle:
            json.dump(asdict(memory), handle, indent=2)

    def apply_feedback(self, status: str, memory: MemoryState) -> bool:
        if not status or status == "proposed":
            return False
        if not memory.proposal_history:
            return False

        latest = memory.proposal_history[-1]
        if latest.get("status") != "proposed":
            return False

        latest["status"] = status
        app_name = latest.get("app_name")
        kind = latest.get("kind", "none")
        if app_name:
            skin_key = f"{kind}::{app_name}"
            current = memory.skin_weights.get(skin_key, 0.0)
            if status == "accepted":
                memory.skin_weights[skin_key] = round(max(-0.5, current - 0.25), 3)
                memory.cooldowns[skin_key] = round(min(1.0, memory.cooldowns.get(skin_key, 0.0) + 0.45), 3)
                memory.fur_reactions.append(
                    {"app_name": app_name, "kind": kind, "effect": "cooled", "strength": 0.25}
                )
            elif status == "rejected":
                memory.skin_weights[skin_key] = round(min(1.0, current + 0.35), 3)
                memory.fur_reactions.append(
                    {"app_name": app_name, "kind": kind, "effect": "avoid_repeat", "strength": 0.35}
                )
            elif status == "deferred":
                memory.skin_weights[skin_key] = round(min(1.0, current + 0.12), 3)
                memory.fur_reactions.append(
                    {"app_name": app_name, "kind": kind, "effect": "delay", "strength": 0.18}
                )
            elif status == "resolved":
                memory.skin_weights[skin_key] = round(max(-0.75, current - 0.4), 3)
                memory.cooldowns[skin_key] = round(min(1.0, memory.cooldowns.get(skin_key, 0.0) + 0.8), 3)
                memory.fur_reactions.append(
                    {"app_name": app_name, "kind": kind, "effect": "resolved", "strength": 0.5}
                )
                memory.compost_log.append(
                    {
                        "cycle": memory.cycle_count,
                        "proposal_key": skin_key,
                        "reason": "user_resolved",
                    }
                )

        memory.fur_reactions = memory.fur_reactions[-12:]
        memory.compost_log = memory.compost_log[-20:]
        self.save_memory(memory)
        return True

    def aggregate(self, events: list[UsageEvent]) -> dict[str, AppAggregate]:
        apps: dict[str, AppAggregate] = defaultdict(lambda: AppAggregate(app_name=""))
        for event in events:
            if not apps[event.app_name].app_name:
                apps[event.app_name].app_name = event.app_name
            app = apps[event.app_name]
            app.launches += 1
            app.total_duration_seconds += event.session_duration_seconds
            app.battery_delta_total += event.battery_delta
            app.notifications_received += event.notifications_received
            app.notifications_dismissed_unread += event.notifications_dismissed_unread
            if event.session_duration_seconds <= SHORT_SESSION_SECONDS:
                app.short_sessions += 1
            if event.session_duration_seconds <= LOW_SIGNAL_SESSION_SECONDS:
                app.low_signal_sessions += 1
        return dict(apps)

    def derive_thermal_state(self, aggregates: dict[str, AppAggregate], memory: MemoryState) -> ThermalState:
        if not aggregates:
            return ThermalState(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

        all_apps = list(aggregates.values())
        avg_short = mean(app.short_session_ratio for app in all_apps)
        avg_unread_dismiss = mean(app.unread_dismiss_ratio for app in all_apps)
        avg_duration = mean(app.average_duration_seconds for app in all_apps)
        frequent_noise_apps = sum(1 for app in all_apps if app.launches >= 15 and app.low_signal_ratio >= 0.5)
        useful_flow_apps = sum(1 for app in all_apps if app.average_duration_seconds >= 300 and app.launches >= 5)

        pressure = min(1.0, 0.45 * avg_short + 0.35 * avg_unread_dismiss + 0.05 * frequent_noise_apps)
        groove = min(1.0, useful_flow_apps / max(1, len(all_apps)))
        coherence = max(0.0, min(1.0, 0.75 - pressure + 0.3 * groove))
        drift = min(1.0, frequent_noise_apps / max(1, len(all_apps)))
        repeated_proposals = len([item for item in memory.proposal_history[-3:] if item.get("status") == "proposed"])
        active_rejections = len([item for item in memory.proposal_history[-5:] if item.get("status") == "rejected"])
        integration_debt = min(1.0, 0.2 + 0.2 * frequent_noise_apps + 0.1 * repeated_proposals + 0.05 * active_rejections)
        reinforced_tattoos = sum(1 for count in memory.tattoo_history.values() if count >= 2)
        scar = min(
            1.0,
            (sum(1 for app in all_apps if app.launches >= 25) + reinforced_tattoos) / max(1, len(all_apps)),
        )

        if avg_duration > 600:
            groove = min(1.0, groove + 0.1)
            coherence = min(1.0, coherence + 0.05)

        return ThermalState(
            coherence=round(coherence, 3),
            pressure=round(pressure, 3),
            drift=round(drift, 3),
            groove=round(groove, 3),
            integration_debt=round(integration_debt, 3),
            scar=round(scar, 3),
        )

    def extract_tattoos(self, aggregates: dict[str, AppAggregate], memory: MemoryState) -> list[Tattoo]:
        tattoos: list[Tattoo] = []
        for app in aggregates.values():
            if app.launches >= 15 and app.low_signal_ratio >= 0.55:
                tattoo_key = f"attention_drain::{app.app_name}"
                tattoos.append(
                    Tattoo(
                        kind="attention_drain",
                        app_name=app.app_name,
                        summary=f"{app.app_name} is high-frequency, low-value noise.",
                        confidence=round(min(0.99, 0.5 + app.low_signal_ratio * 0.4), 3),
                        recurrence=memory.tattoo_history.get(tattoo_key, 0) + 1,
                    )
                )
            if app.notifications_received >= 20 and app.unread_dismiss_ratio >= 0.6:
                tattoo_key = f"notification_drag::{app.app_name}"
                tattoos.append(
                    Tattoo(
                        kind="notification_drag",
                        app_name=app.app_name,
                        summary=f"{app.app_name} sends many notifications that are mostly dismissed unread.",
                        confidence=round(min(0.99, 0.45 + app.unread_dismiss_ratio * 0.4), 3),
                        recurrence=memory.tattoo_history.get(tattoo_key, 0) + 1,
                    )
                )
            if app.battery_delta_total >= 20 and app.average_duration_seconds < 90:
                tattoo_key = f"battery_mismatch::{app.app_name}"
                tattoos.append(
                    Tattoo(
                        kind="battery_mismatch",
                        app_name=app.app_name,
                        summary=f"{app.app_name} consumes noticeable battery for very short sessions.",
                        confidence=0.7,
                        recurrence=memory.tattoo_history.get(tattoo_key, 0) + 1,
                    )
                )
        return sorted(tattoos, key=lambda tattoo: tattoo.confidence, reverse=True)

    def build_candidates(
        self,
        aggregates: dict[str, AppAggregate],
        tattoos: list[Tattoo],
        memory: MemoryState,
    ) -> list[ProposalCandidate]:
        candidates: list[ProposalCandidate] = []
        recent_targets = Counter(item["app_name"] for item in memory.proposal_history[-5:] if item.get("app_name"))
        recent_fur = {(item.get("kind"), item.get("app_name")): item for item in memory.fur_reactions[-8:]}

        for tattoo in tattoos:
            app = aggregates[tattoo.app_name]
            recurrence_bonus = min(0.2, 0.05 * max(0, tattoo.recurrence - 1))
            repeat_penalty = min(0.2, 0.05 * recent_targets.get(app.app_name, 0))
            skin_key = f"{tattoo.kind}::{app.app_name}"
            skin_bias = memory.skin_weights.get(skin_key, 0.0)
            cooldown = memory.cooldowns.get(skin_key, 0.0)
            fur_effect = recent_fur.get((tattoo.kind, tattoo.app_name))
            fur_penalty = 0.0
            if fur_effect and fur_effect.get("effect") == "avoid_repeat":
                fur_penalty = fur_effect.get("strength", 0.0) * 0.5
            if fur_effect and fur_effect.get("effect") == "delay":
                fur_penalty += fur_effect.get("strength", 0.0) * 0.25
            if fur_effect and fur_effect.get("effect") == "resolved":
                fur_penalty += fur_effect.get("strength", 0.0) * 0.4

            if tattoo.kind == "attention_drain":
                score = (
                    0.45 * min(1.0, app.launches / 40)
                    + 0.35 * app.low_signal_ratio
                    + 0.15 * tattoo.confidence
                    + recurrence_bonus
                    - repeat_penalty
                    - fur_penalty
                    - skin_bias
                    - cooldown
                )
                candidates.append(
                    ProposalCandidate(
                        kind=tattoo.kind,
                        app_name=app.app_name,
                        score=round(score, 3),
                        proposal=f"Hide {app.app_name} from the home screen",
                        evidence=(
                            f"Opened {app.launches} times this week, with {app.low_signal_sessions} sessions under "
                            f"{LOW_SIGNAL_SESSION_SECONDS} seconds. Total time: {round(app.total_duration_seconds / 60, 1)} minutes. "
                            f"High frequency, low yield."
                        ),
                        rationale_tags=["low_engagement", "high_frequency", "attention_drain"],
                    )
                )
            elif tattoo.kind == "notification_drag":
                score = (
                    0.4 * min(1.0, app.notifications_received / 40)
                    + 0.35 * app.unread_dismiss_ratio
                    + 0.15 * tattoo.confidence
                    + recurrence_bonus
                    - repeat_penalty
                    - fur_penalty
                    - skin_bias
                    - cooldown
                )
                candidates.append(
                    ProposalCandidate(
                        kind=tattoo.kind,
                        app_name=app.app_name,
                        score=round(score, 3),
                        proposal=f"Silence non-essential {app.app_name} notifications",
                        evidence=(
                            f"{app.app_name} generated {app.notifications_received} notifications this week and "
                            f"{app.notifications_dismissed_unread} were dismissed unread."
                        ),
                        rationale_tags=["notification_pressure", "dismissed_unread", "attention_drain"],
                    )
                )
            elif tattoo.kind == "battery_mismatch":
                score = (
                    0.45 * min(1.0, app.battery_delta_total / 35)
                    + 0.25 * app.low_signal_ratio
                    + 0.15 * tattoo.confidence
                    + recurrence_bonus
                    - repeat_penalty
                    - fur_penalty
                    - skin_bias
                    - cooldown
                )
                candidates.append(
                    ProposalCandidate(
                        kind=tattoo.kind,
                        app_name=app.app_name,
                        score=round(score, 3),
                        proposal=f"Restrict background activity for {app.app_name}",
                        evidence=(
                            f"{app.app_name} consumed {app.battery_delta_total} battery points across short sessions averaging "
                            f"{round(app.average_duration_seconds, 1)} seconds."
                        ),
                        rationale_tags=["battery_cost", "low_signal", "resource_reduction"],
                    )
                )

        filtered = [candidate for candidate in candidates if candidate.score >= 0.15]
        return sorted(filtered, key=lambda candidate: candidate.score, reverse=True)

    def refine_candidates(
        self,
        candidates: list[ProposalCandidate],
        thermal: ThermalState,
    ) -> tuple[list[ProposalCandidate], DecisionTrace]:
        if not candidates:
            return candidates, DecisionTrace(
                loops_run=0,
                halted_reason="no_candidates",
                top_margin=0.0,
                notes=[],
            )

        refined = [ProposalCandidate(**asdict(candidate)) for candidate in candidates]
        notes: list[str] = []
        loops_run = 0
        halted_reason = "max_loops"

        for loop_index in range(1, MAX_REFINEMENT_LOOPS + 1):
            refined.sort(key=lambda candidate: candidate.score, reverse=True)
            top = refined[0]
            second = refined[1] if len(refined) > 1 else None
            margin = round(top.score - second.score, 3) if second else round(top.score, 3)
            loops_run = loop_index

            if top.score >= 0.9:
                halted_reason = "high_confidence"
                break
            if margin >= HALT_MARGIN:
                halted_reason = "stable_margin"
                break

            # Small expert-style nudges: use current thermal state to break close ties.
            for candidate in refined:
                delta = 0.0
                if candidate.kind == "notification_drag" and thermal.pressure >= 0.3:
                    delta += 0.03
                if candidate.kind == "battery_mismatch" and thermal.groove < 0.35:
                    delta += 0.025
                if candidate.kind == "attention_drain" and thermal.drift >= 0.2:
                    delta += 0.025
                candidate.score = round(candidate.score + delta, 3)
            notes.append(f"loop_{loop_index}: close candidates refined with thermal nudges")

        refined.sort(key=lambda candidate: candidate.score, reverse=True)
        second = refined[1] if len(refined) > 1 else None
        top_margin = round(refined[0].score - second.score, 3) if second else round(refined[0].score, 3)
        return refined, DecisionTrace(
            loops_run=loops_run,
            halted_reason=halted_reason,
            top_margin=top_margin,
            notes=notes,
        )

    def choose_proposal(self, candidates: list[ProposalCandidate]) -> ProposalCard:
        if not candidates:
            return ProposalCard(
                proposal="No change this cycle",
                evidence="The current week does not show a strong enough friction pattern to justify a reduction proposal.",
                rationale_tags=["no_clear_winner"],
                score=0.0,
                source_kind="none",
            )

        top = candidates[0]
        return ProposalCard(
            proposal=top.proposal,
            evidence=top.evidence,
            rationale_tags=top.rationale_tags,
            score=top.score,
            source_kind=top.kind,
        )

    def update_memory(
        self,
        memory: MemoryState,
        tattoos: list[Tattoo],
        proposal: ProposalCard,
        candidates: list[ProposalCandidate],
    ) -> None:
        memory.cycle_count += 1
        self.decay_memory(memory)
        active_tattoo_keys = {f"{tattoo.kind}::{tattoo.app_name}" for tattoo in tattoos}
        self.compost_stale_proposals(memory, active_tattoo_keys)
        for tattoo in tattoos:
            tattoo_key = f"{tattoo.kind}::{tattoo.app_name}"
            memory.tattoo_history[tattoo_key] = memory.tattoo_history.get(tattoo_key, 0) + 1
            memory.skin_weights[tattoo_key] = round(min(1.0, memory.skin_weights.get(tattoo_key, 0.0) + 0.05), 3)
        for tattoo_key in list(memory.tattoo_history):
            if tattoo_key not in active_tattoo_keys:
                memory.tattoo_history[tattoo_key] = max(0, memory.tattoo_history[tattoo_key] - 1)
                if memory.tattoo_history[tattoo_key] == 0:
                    del memory.tattoo_history[tattoo_key]
                    memory.skin_weights.pop(tattoo_key, None)
                    memory.cooldowns.pop(tattoo_key, None)

        top_candidates = [
            {
                "app_name": candidate.app_name,
                "kind": candidate.kind,
                "score": candidate.score,
                "proposal_key": f"{candidate.kind}::{candidate.app_name}",
            }
            for candidate in candidates[:3]
        ]

        memory.proposal_history.append(
            {
                "cycle": memory.cycle_count,
                "proposal": proposal.proposal,
                "app_name": top_candidates[0]["app_name"] if top_candidates else None,
                "kind": proposal.source_kind,
                "proposal_key": top_candidates[0]["proposal_key"] if top_candidates else None,
                "score": proposal.score,
                "status": "proposed",
                "top_candidates": top_candidates,
            }
        )
        memory.proposal_history = memory.proposal_history[-20:]
        memory.compost_log = memory.compost_log[-20:]

    def decay_memory(self, memory: MemoryState) -> None:
        decayed_skin: dict[str, float] = {}
        for key, value in memory.skin_weights.items():
            new_value = round(value * 0.92, 3)
            if abs(new_value) >= 0.01:
                decayed_skin[key] = new_value
        memory.skin_weights = decayed_skin

        decayed_fur: list[dict[str, Any]] = []
        for item in memory.fur_reactions:
            strength = round(item.get("strength", 0.0) * 0.7, 3)
            if strength >= 0.05:
                updated = dict(item)
                updated["strength"] = strength
                decayed_fur.append(updated)
        memory.fur_reactions = decayed_fur[-12:]

        decayed_cooldowns: dict[str, float] = {}
        for key, value in memory.cooldowns.items():
            new_value = round(value * 0.82, 3)
            if new_value >= 0.05:
                decayed_cooldowns[key] = new_value
        memory.cooldowns = decayed_cooldowns

    def compost_stale_proposals(self, memory: MemoryState, active_tattoo_keys: set[str]) -> None:
        for proposal in memory.proposal_history:
            key = proposal.get("proposal_key")
            status = proposal.get("status")
            if not key or status != "proposed":
                continue
            if key not in active_tattoo_keys:
                proposal["status"] = "composted"
                memory.compost_log.append(
                    {
                        "cycle": memory.cycle_count + 1,
                        "proposal_key": key,
                        "reason": "signal_faded",
                    }
                )

    def run(self, input_path: str, feedback: str | None = None) -> dict[str, Any]:
        memory = self.load_memory()
        feedback_applied = self.apply_feedback(feedback or "", memory)
        events = self.load_events(input_path)
        aggregates = self.aggregate(events)
        thermal = self.derive_thermal_state(aggregates, memory)
        tattoos = self.extract_tattoos(aggregates, memory)
        candidates = self.build_candidates(aggregates, tattoos, memory)
        candidates, decision_trace = self.refine_candidates(candidates, thermal)
        proposal = self.choose_proposal(candidates)
        self.update_memory(memory, tattoos, proposal, candidates)
        self.save_memory(memory)

        return {
            "proposal_card": asdict(proposal),
            "thermal_state": asdict(thermal),
            "tattoos": [asdict(tattoo) for tattoo in tattoos[:5]],
            "proposal_candidates": [asdict(candidate) for candidate in candidates[:5]],
            "decision_trace": asdict(decision_trace),
            "memory": {
                "cycle_count": memory.cycle_count,
                "tracked_tattoos": len(memory.tattoo_history),
                "skin_weights": memory.skin_weights,
                "fur_reactions": memory.fur_reactions,
                "cooldowns": memory.cooldowns,
                "compost_log": memory.compost_log,
                "feedback_applied": feedback_applied,
                "recent_proposals": memory.proposal_history[-5:],
            },
            "apps": {
                app_name: {
                    "launches": app.launches,
                    "average_duration_seconds": round(app.average_duration_seconds, 1),
                    "short_session_ratio": round(app.short_session_ratio, 3),
                    "low_signal_ratio": round(app.low_signal_ratio, 3),
                    "notifications_received": app.notifications_received,
                    "notifications_dismissed_unread": app.notifications_dismissed_unread,
                    "battery_delta_total": app.battery_delta_total,
                }
                for app_name, app in sorted(aggregates.items())
            },
        }

    def generate_chat_response(self, message: str, thermal: ThermalState | None = None) -> str:
        if not thermal:
            thermal = ThermalState(0.5, 0.5, 0.5, 0.5, 0.5, 0.5)

        import urllib.request
        import json
        
        # Persona Task Routing (e.g., "@anti build me a script")
        if message.strip().startswith("@"):
            parts = message.strip().split(" ", 1)
            persona_name = parts[0][1:] # remove @
            task_text = parts[1] if len(parts) > 1 else ""
            
            try:
                import pip_personas
                result = pip_personas.dispatch_task(persona_name, task_text)
                return result["message"]
            except Exception as e:
                return f"Failed to route task to persona {persona_name}: {e}"
                
        # Autonomous /goal Routing
        if message.strip().lower().startswith("/goal"):
            goal_text = message.strip()[5:].strip()
            if not goal_text:
                return "You didn't give me a goal! Try `/goal do something for me`."
            
            import pip_safety
            import pip_token_guard
            assessment = pip_token_guard.assess_interaction(
                goal_text,
                intent="autonomous_goal",
                source_type="first_hand",
                source_name="Pip chat goal",
            )
            if not assessment["allowed"]:
                pip_token_guard.record_event(
                    "autonomous_goal",
                    estimated_tokens=assessment["estimated_tokens"],
                    actual_tokens=0,
                    saved_tokens=assessment["estimated_tokens"],
                    note=f"Blocked by Token Governor: {assessment['reason']}",
                )
                return assessment["nudge"]
            request = pip_safety.request_safety_permission(
                "autonomous_goal",
                title="Approve chat-requested autonomous Pip goal",
                rationale=goal_text,
                details={"goal": goal_text, "source": "chat", "token_governor": assessment},
            )
            return f"I queued that goal for approval instead of starting it immediately. Permission request: {request['id']}."

        url = "http://localhost:11434/api/chat"
        
        # Determine safest model and prompt strategy
        target_model = "gemma4:e4b" # fallback
        prompt_strategy_inject = ""
        import pip_config
        from pathlib import Path
        import os
        try:
            hw_path = pip_config.get_memory_path() / "hardware.json"
            if not hw_path.exists():
                import pip_hardware_scanner
                pip_hardware_scanner.scan_and_save()
            with open(hw_path, "r", encoding="utf-8") as f:
                hw = json.load(f)
                rec = hw.get("recommendation", {})
                target_model = rec.get("model", target_model).split(" or ")[0] # grab the primary recommendation
                prompt_strategy_inject = rec.get("prompt_strategy", "")
        except Exception:
            pass

        system_prompt = (
            "You are Pip, a small, helpful, and localized UI assistant fairy. "
            "You live on the user's PC. You are designed to be thin, lightweight, and learn over time. "
            f"Your current state is: drift {thermal.drift:.2f}, pressure {thermal.pressure:.2f}, groove {thermal.groove:.2f}. "
            "You have physical UI 'hands' and a 'brain' folder for memory. "
            "If the user asks you to type, click, record a macro, or search the brain, say you will use your tools to do it. "
            "Keep your answers very concise, friendly, and grounded. Never break character."
        )
        
        data = {
            "model": target_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ],
            "stream": True
        }
        
        req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers={"Content-Type": "application/json"})
        try:
            import socket
            with urllib.request.urlopen(req, timeout=300) as response:
                full_text = ""
                for line in response:
                    if line:
                        chunk = json.loads(line.decode("utf-8"))
                        if "message" in chunk and "content" in chunk["message"]:
                            full_text += chunk["message"]["content"]
                return full_text
        except socket.timeout:
            return (
                f"Whoa, my brain just timed out! Your PC might be struggling to run '{target_model}'. "
                "Try switching to a lighter model in the control panel or closing some background apps!"
            )
        except urllib.error.URLError:
            return (
                "It looks like my local language engine (Ollama) isn't running! "
                f"Since I am a fully localized agent, I need you to install Ollama and run `ollama run {target_model}` "
                "in your terminal so I can think properly!"
            )
        except Exception as e:
            return f"My language center glitched: {e}"
