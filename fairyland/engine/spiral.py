"""
Spiral Engine — the core loop.

INPUT -> (t) interpret -> (.) hold -> narrow -> (T) structure -> respond -> loop

The engine transitions through five states:
  HANDSHAKE -> ANCHOR -> HOLD -> RENDER -> RITUAL -> (loop)

Now integrated with:
  - Oscillator (phi-driven mode transitions)
  - Rich sensing (rhythm, repetition, trajectory)
  - Micro-healing interventions
  - Bias drift tracking
  - Mode effects on pressure/decay/reveal
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from .drift import DriftNudge, DriftTracker
from .healing import Intervention, select_intervention
from .oscillator import ModeEffect, advance_oscillator, mode_effects
from .sensing import TextSignals, extract_signals
from .state import (
    BreathState,
    KernelState,
    MacroContext,
    MicroContext,
    Mode,
    PipContext,
    RuntimeState,
    SessionMode,
    SpiralState,
)


# ---------------------------------------------------------------------------
# Signal interpretation (kept for biome — tone moved to sensing.py)
# ---------------------------------------------------------------------------

def _detect_biome_hint(text: str) -> Optional[str]:
    text_lower = text.lower()
    biome_keywords = {
        "forest": ["forest", "wood", "tree", "oak", "pine", "birch", "canopy"],
        "meadow": ["meadow", "field", "grass", "flower", "wildflower"],
        "wetland": ["pond", "stream", "river", "marsh", "bog", "wetland", "lake"],
        "coast": ["beach", "coast", "shore", "sea", "ocean", "tide", "rock pool"],
        "garden": ["garden", "yard", "lawn", "hedge", "fence"],
        "urban": ["park", "pavement", "wall", "crack", "street", "city"],
    }
    for biome, kws in biome_keywords.items():
        if any(kw in text_lower for kw in kws):
            return biome
    return None


def _compute_pressure(text: str, state: RuntimeState, signals: TextSignals,
                      pressure_baseline: float = 0.0) -> float:
    """
    Compute kernel pressure with feedback loops.

    Integrates:
      - Previous pressure momentum
      - Text signals (rhythm, repetition, trajectory)
      - Coherence-pressure coupling
      - Oscillator mode damping
      - Historical pressure baseline from tattoos
    """
    k = state.kernel
    osc_effect = mode_effects(state.oscillator.mode)

    # base momentum — previous pressure decays
    momentum = k.pressure * 0.35

    # text-derived pressure
    length_factor = min(len(text) / 200.0, 0.25)
    exclamation_factor = min(text.count("!") * 0.08, 0.25)
    question_factor = min(text.count("?") * 0.04, 0.12)

    # rhythm: staccato raises pressure, flowing lowers it
    rhythm_factor = {"staccato": 0.08, "mixed": 0.0, "flowing": -0.05}.get(signals.rhythm, 0.0)

    # repetition amplifies pressure (looping = stress)
    repetition_factor = signals.repetition_score * 0.25

    # trajectory: escalating adds pressure, settling removes it
    trajectory_factor = {
        "escalating": 0.12, "flat": 0.0, "settling": -0.08
    }.get(signals.emotional_direction, 0.0)

    # burst: raw input intensity. Zero for text; for touch it carries the
    # cadence that text would otherwise express through length/exclamations.
    burst_factor = signals.burst_score * 0.2

    # coherence-pressure coupling: low coherence amplifies pressure
    coherence_coupling = (1.0 - k.coherence) * 0.1

    # historical baseline from tattoos
    baseline = max(-0.1, min(0.1, pressure_baseline))

    raw = (momentum + length_factor + exclamation_factor + question_factor +
           rhythm_factor + repetition_factor + trajectory_factor +
           burst_factor + coherence_coupling + baseline)

    # apply oscillator mode damping
    raw *= osc_effect.pressure_damping

    return max(0.0, min(1.0, raw))


# ---------------------------------------------------------------------------
# Spiral output
# ---------------------------------------------------------------------------

@dataclass
class SpiralOutput:
    """What the engine emits after one step."""
    text: str
    state_name: str
    breath: str
    anchor: Optional[str] = None
    pip_active: bool = False
    ritual_question: Optional[str] = None
    weather: Optional[Dict[str, str]] = None
    intervention: Optional[str] = None
    drift_nudge: Optional[str] = None
    oscillator_mode: Optional[str] = None
    signals: Optional[Dict] = None


_RITUAL_QUESTIONS = [
    "What did you notice that you almost missed?",
    "What's the smallest thing near you right now?",
    "Can you hear something you weren't listening to before?",
    "What colour is the light where you are?",
    "If you close your eyes, what do you feel under your hands?",
    "What's the temperature of the air on your skin right now?",
]

_ANCHORS = ["Make", "Sit", "Read", "Walk", "Find"]


class SpiralEngine:
    """
    The core Fairyland engine.

    Runs the five-state spiral loop and manages the three-register
    context ((t), (.), (T)). Integrates oscillator, sensing, healing,
    and drift tracking.
    """

    def __init__(self, state: Optional[RuntimeState] = None,
                 pressure_baseline: float = 0.0):
        self.state = state or RuntimeState()
        self._ritual_idx = 0
        self._drift = DriftTracker()
        self._pressure_baseline = pressure_baseline
        self._last_signals: Optional[TextSignals] = None
        self._last_anchor_tick = 0

    # -- public API ---------------------------------------------------------

    def step(self, text: str) -> SpiralOutput:
        """Process one user input through the spiral."""
        self.state.tick += 1

        # (t) — extract rich signals
        signals = extract_signals(text, self.state.history)
        self._last_signals = signals
        self._sense(text, signals)

        # advance oscillator
        self.state.oscillator = advance_oscillator(
            self.state.oscillator, self.state.kernel, self.state.tick
        )

        # pressure / kernel / breath update
        self._update_kernel(text, signals)
        self._update_breath()

        # check for drift nudge
        drift_nudge = self._drift.update(
            text,
            repetition_score=signals.repetition_score,
            tick=self.state.tick,
            tone=signals.tone,
        )

        # overdrive check — Pip interrupt
        if self.state.breath == BreathState.OVERDRIVE:
            out = self._pip_interrupt()
            out.oscillator_mode = self.state.oscillator.mode.name
            return out

        # state machine transition
        output = self._advance(text)

        # attach oscillator mode
        output.oscillator_mode = self.state.oscillator.mode.name

        # check for micro-healing intervention
        intervention = select_intervention(
            self.state.kernel, self.state.oscillator.mode
        )
        if intervention:
            output.intervention = intervention.artifact

        # attach drift nudge (replaces output text if parasocial)
        if drift_nudge:
            output.drift_nudge = drift_nudge.text

        # attach signal summary for transparency
        output.signals = {
            "tone": signals.tone,
            "rhythm": signals.rhythm,
            "repetition": round(signals.repetition_score, 2),
            "trajectory": signals.emotional_direction,
            "density": round(signals.word_density, 2),
        }

        return output

    def rhythm_step(self, signals: TextSignals) -> SpiralOutput:
        """Process one canvas telemetry batch. No words in, no words out.

        Kids-mode contract (v14): the system mirrors energy only. The kernel,
        breath, oscillator and drift all update from rhythm, but the output
        carries no text, no labels, no scores — just breath state, the Pip
        interrupt when overdriven, an anchor verb when calm, and weather.
        """
        self.state.tick += 1
        self._last_signals = signals

        # advance oscillator
        self.state.oscillator = advance_oscillator(
            self.state.oscillator, self.state.kernel, self.state.tick
        )

        # kernel and breath update from rhythm alone (empty text contributes
        # nothing; pressure moves on rhythm/repetition/trajectory factors)
        self._update_kernel("", signals)
        self._update_breath()

        # echo drift still applies to touch loops; parasocial/narrowing
        # need words and simply stay quiet
        self._drift.update(
            "",
            repetition_score=signals.repetition_score,
            tick=self.state.tick,
            tone=None,
        )

        # overdrive — Pip silence interrupt
        if self.state.breath == BreathState.OVERDRIVE:
            out = self._pip_interrupt()
            out.text = ""
            out.oscillator_mode = self.state.oscillator.mode.name
            out.weather = self.get_weather()
            return out

        # the silence has passed — release the hold (the text path does this
        # in _do_hold; the canvas has no next utterance to do it for us)
        if self.state.context.pip.active:
            self.state.context.pip.active = False
            self.state.context.pip.hold_reason = None

        # anchor verb: only when calm or open, and only occasionally
        anchor = None
        if (self.state.breath in (BreathState.CALM, BreathState.FLOW)
                and self.state.oscillator.mode != Mode.SHED
                and self.state.tick - self._last_anchor_tick >= 8):
            anchor = _ANCHORS[self._ritual_idx % len(_ANCHORS)]
            self._ritual_idx += 1
            self._last_anchor_tick = self.state.tick

        return SpiralOutput(
            text="",
            state_name=self.state.spiral.value,
            breath=self.state.breath.value,
            anchor=anchor,
            pip_active=False,
            weather=self.get_weather(),
            oscillator_mode=self.state.oscillator.mode.name,
        )

    def set_mode(self, mode: SessionMode):
        self.state.context.T.mode = mode

    def get_weather(self) -> Dict[str, str]:
        """Parent-mode weather: rhythm, tension, flow. No content."""
        k = self.state.kernel
        rhythm = "resting" if k.groove > 0.6 else ("steady" if k.groove > 0.3 else "busy")
        tension = "low" if k.pressure < 0.3 else ("passing" if k.pressure < 0.6 else "held")
        flow = "exploratory" if k.temperature > 0.5 else "repetitive"
        return {"rhythm": rhythm, "tension": tension, "flow": flow}

    def get_drift_hud(self) -> dict:
        """Return bias drift HUD."""
        return self._drift.get_hud()

    @property
    def last_signals(self) -> Optional[TextSignals]:
        return self._last_signals

    # -- (t) sense ----------------------------------------------------------

    def _sense(self, text: str, signals: TextSignals):
        t = self.state.context.t
        t.last_input = text
        t.tone = signals.tone
        t.mood = signals.emotional_direction

    # -- kernel / breath ----------------------------------------------------

    def _update_kernel(self, text: str, signals: TextSignals):
        k = self.state.kernel
        osc_effect = mode_effects(self.state.oscillator.mode)

        # pressure with full feedback
        k.pressure = _compute_pressure(text, self.state, signals, self._pressure_baseline)

        # coherence decays toward pressure, modulated by oscillator
        coherence_target = 1.0 - k.pressure
        k.coherence = k.coherence * 0.8 + coherence_target * 0.2

        # groove settles — good rhythm when pressure is moderate
        groove_target = 1.0 - abs(k.pressure - 0.3)
        k.groove = k.groove * 0.85 + groove_target * 0.15

        # temperature: novelty raises, repetition lowers
        if signals.repetition_score > 0.5:
            k.temperature = max(0.0, k.temperature - 0.08)
        elif signals.word_density > 0.7:
            k.temperature = min(1.0, k.temperature + 0.06)
        else:
            k.temperature = min(1.0, k.temperature + 0.03)

        # stress accumulates with sustained pressure, recovers in DWELL
        if k.pressure > 0.5:
            k.stress = min(1.0, k.stress + 0.03)
        else:
            k.stress = max(0.0, k.stress - 0.02 * (1.0 + osc_effect.decay_rate))

        # reserve depletes under load, recovers when calm
        if k.pressure > 0.6:
            k.reserve = max(0.0, k.reserve - 0.02)
        else:
            k.reserve = min(1.0, k.reserve + 0.01)

        # recovery tracks how well the system bounces back
        k.recovery = k.recovery * 0.9 + (1.0 - k.stress) * 0.1

        # debt accumulates when reserve is low
        if k.reserve < 0.3:
            k.debt = min(1.0, k.debt + 0.02)
        else:
            k.debt = max(0.0, k.debt - 0.01)

        # loss tracks when coherence drops sharply
        if k.coherence < 0.4:
            k.loss = min(1.0, k.loss + 0.03)
        else:
            k.loss = max(0.0, k.loss - 0.02)

    def _update_breath(self):
        p = self.state.kernel.pressure
        if p > 0.8:
            self.state.breath = BreathState.OVERDRIVE
        elif p > 0.55:
            self.state.breath = BreathState.EDGE
        elif p > 0.3:
            self.state.breath = BreathState.FLOW
        else:
            self.state.breath = BreathState.CALM

    # -- Pip interrupt ------------------------------------------------------

    def _pip_interrupt(self) -> SpiralOutput:
        self.state.context.pip.active = True
        self.state.context.pip.hold_reason = "overdrive"
        self.state.spiral = SpiralState.HOLD
        return SpiralOutput(
            text="(.) …",
            state_name=SpiralState.HOLD.value,
            breath=BreathState.OVERDRIVE.value,
            pip_active=True,
        )

    # -- state machine ------------------------------------------------------

    def _advance(self, text: str) -> SpiralOutput:
        s = self.state.spiral

        if s == SpiralState.HANDSHAKE:
            return self._do_handshake(text)
        elif s == SpiralState.ANCHOR:
            return self._do_anchor(text)
        elif s == SpiralState.HOLD:
            return self._do_hold(text)
        elif s == SpiralState.RENDER:
            return self._do_render(text)
        elif s == SpiralState.RITUAL:
            return self._do_ritual(text)

        return self._do_handshake(text)

    def _do_handshake(self, text: str) -> SpiralOutput:
        """Name + mode selection."""
        text_lower = text.lower().strip()

        if any(w in text_lower for w in ["kid", "child", "young"]):
            self.set_mode(SessionMode.KID)
        elif any(w in text_lower for w in ["code", "coder", "dev", "developer"]):
            self.set_mode(SessionMode.CODER)
        else:
            self.set_mode(SessionMode.ADULT)

        self.state.spiral = SpiralState.ANCHOR
        self.state.history.append({"state": "HANDSHAKE", "input": text})

        mode_label = self.state.context.T.mode.value.lower()
        return SpiralOutput(
            text=f"Welcome. {mode_label.title()} mode. What are you near?",
            state_name=SpiralState.ANCHOR.value,
            breath=self.state.breath.value,
        )

    def _do_anchor(self, text: str) -> SpiralOutput:
        """Biome or species anchoring."""
        biome = _detect_biome_hint(text)
        self.state.context.T.biome = biome

        self.state.history.append({"state": "ANCHOR", "input": text, "biome": biome})

        if biome:
            self.state.spiral = SpiralState.RENDER
            return SpiralOutput(
                text=f"Good. {biome.title()}.",
                state_name=SpiralState.RENDER.value,
                breath=self.state.breath.value,
            )

        self.state.context.pip.active = True
        self.state.context.pip.question = "Can you describe what's around you?"
        self.state.spiral = SpiralState.HOLD
        return SpiralOutput(
            text="Can you describe what's around you?",
            state_name=SpiralState.HOLD.value,
            breath=self.state.breath.value,
            pip_active=True,
        )

    def _do_hold(self, text: str) -> SpiralOutput:
        """(.) Ambiguity allowed — ask one clarifier, stay aesthetic."""
        self.state.context.pip.active = False

        biome = _detect_biome_hint(text)
        if biome:
            self.state.context.T.biome = biome

        self.state.history.append({"state": "HOLD", "input": text})
        self.state.spiral = SpiralState.RENDER

        if self.state.context.T.mode == SessionMode.KID:
            return SpiralOutput(
                text="Let's see what's here.",
                state_name=SpiralState.RENDER.value,
                breath=self.state.breath.value,
            )

        return SpiralOutput(
            text="Noted. Let's look closer.",
            state_name=SpiralState.RENDER.value,
            breath=self.state.breath.value,
        )

    def _do_render(self, text: str) -> SpiralOutput:
        """Show plant/media card + safety. Kid mode: never ID plants directly."""
        self.state.history.append({"state": "RENDER", "input": text})

        mode = self.state.context.T.mode
        tone = self.state.context.t.tone
        osc_effect = mode_effects(self.state.oscillator.mode)

        # in DWELL mode, responses are shorter and more reflective
        dwell_prefix = "" if not self.state.oscillator.in_dwell else "Slowly now. "

        if mode == SessionMode.KID:
            if tone == "cautious":
                reply = "A plant that protects itself. Did you notice where it grows?"
            elif tone == "curious":
                reply = "Something caught your eye. What shape are the leaves?"
            elif tone == "excited":
                reply = "You found something! What does it feel like — rough, smooth, waxy?"
            elif tone == "withdrawn":
                reply = "It's here. You're here. That's enough."
            else:
                reply = "Look closely. What do you notice first?"
        elif mode == SessionMode.CODER:
            reply = f"Biome: {self.state.context.T.biome or 'unknown'}. Observation logged."
        else:
            if tone == "cautious":
                reply = "Something with defences. Notice the habitat — that's the first clue."
            elif tone == "curious":
                reply = "Good eye. Leaf shape and arrangement tell you a lot."
            elif tone == "withdrawn":
                reply = "No rush. Just notice what's closest."
            elif tone == "confused":
                reply = "Stay with what you see. The shape. The texture. Names come later."
            else:
                reply = "Observe the growth pattern. Where does it sit relative to light and water?"

        self.state.spiral = SpiralState.RITUAL
        return SpiralOutput(
            text=dwell_prefix + reply,
            state_name=SpiralState.RITUAL.value,
            breath=self.state.breath.value,
        )

    def _do_ritual(self, text: str) -> SpiralOutput:
        """End with one noticing question. Attention outward. Then loop."""
        self.state.history.append({"state": "RITUAL", "input": text})

        question = _RITUAL_QUESTIONS[self._ritual_idx % len(_RITUAL_QUESTIONS)]
        self._ritual_idx += 1

        # pick an anchor if calm
        anchor = None
        if self.state.breath in (BreathState.CALM, BreathState.FLOW):
            anchor = _ANCHORS[self._ritual_idx % len(_ANCHORS)]

        self.state.spiral = SpiralState.RENDER

        return SpiralOutput(
            text=question,
            state_name=SpiralState.RENDER.value,
            breath=self.state.breath.value,
            anchor=anchor,
            ritual_question=question,
            weather=self.get_weather(),
        )
