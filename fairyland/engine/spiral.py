"""
Spiral Engine — the core loop.

INPUT -> (t) interpret -> (.) hold -> narrow -> (T) structure -> respond -> loop

The engine transitions through five states:
  HANDSHAKE -> ANCHOR -> HOLD -> RENDER -> RITUAL -> (loop)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional

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
# Signal interpretation
# ---------------------------------------------------------------------------

# Simple keyword-based tone detection (no ML, just presence heuristics)
_TONE_SIGNALS = {
    "curious": ["what", "how", "why", "tell me", "wonder", "?"],
    "confused": ["don't understand", "huh", "what do you mean", "confused", "lost"],
    "excited": ["wow", "cool", "amazing", "awesome", "!"],
    "cautious": ["careful", "sting", "hurt", "sharp", "danger", "scary"],
    "calm": ["nice", "pretty", "peaceful", "soft", "gentle"],
}


def _detect_tone(text: str) -> Optional[str]:
    text_lower = text.lower()
    scores = {}
    for tone, keywords in _TONE_SIGNALS.items():
        scores[tone] = sum(1 for kw in keywords if kw in text_lower)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else None


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


def _compute_pressure(text: str, state: RuntimeState) -> float:
    """Estimate kernel pressure from input signals."""
    pressure = state.kernel.pressure
    length_factor = min(len(text) / 200.0, 0.3)
    exclamation_factor = min(text.count("!") * 0.1, 0.3)
    question_factor = min(text.count("?") * 0.05, 0.15)
    repetition = 0.0
    if state.context.t.last_input and text.strip() == state.context.t.last_input.strip():
        repetition = 0.3

    raw = pressure * 0.4 + length_factor + exclamation_factor + question_factor + repetition
    return max(0.0, min(1.0, raw))


# ---------------------------------------------------------------------------
# Spiral state transitions
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
    context ((t), (.), (T)).
    """

    def __init__(self, state: Optional[RuntimeState] = None):
        self.state = state or RuntimeState()
        self._ritual_idx = 0

    # -- public API ---------------------------------------------------------

    def step(self, text: str) -> SpiralOutput:
        """Process one user input through the spiral."""
        self.state.tick += 1

        # (t) — micro observation
        self._sense(text)

        # pressure / breath update
        self._update_kernel(text)
        self._update_breath()

        # overdrive check — Pip interrupt
        if self.state.breath == BreathState.OVERDRIVE:
            return self._pip_interrupt()

        # state machine transition
        return self._advance(text)

    def set_mode(self, mode: SessionMode):
        self.state.context.T.mode = mode

    def get_weather(self) -> Dict[str, str]:
        """Parent-mode weather: rhythm, tension, flow. No content."""
        k = self.state.kernel
        rhythm = "resting" if k.groove > 0.6 else ("steady" if k.groove > 0.3 else "busy")
        tension = "low" if k.pressure < 0.3 else ("passing" if k.pressure < 0.6 else "held")
        flow = "exploratory" if k.temperature > 0.5 else "repetitive"
        return {"rhythm": rhythm, "tension": tension, "flow": flow}

    # -- (t) sense ----------------------------------------------------------

    def _sense(self, text: str):
        t = self.state.context.t
        t.last_input = text
        t.tone = _detect_tone(text)

    # -- kernel / breath ----------------------------------------------------

    def _update_kernel(self, text: str):
        k = self.state.kernel
        k.pressure = _compute_pressure(text, self.state)
        # coherence decays toward pressure
        k.coherence = k.coherence * 0.8 + (1.0 - k.pressure) * 0.2
        # groove settles
        k.groove = k.groove * 0.9 + 0.1 * (1.0 - abs(k.pressure - 0.3))
        # temperature rises with novelty, falls with repetition
        if self.state.context.t.last_input == text:
            k.temperature = max(0.0, k.temperature - 0.1)
        else:
            k.temperature = min(1.0, k.temperature + 0.05)

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

        # fallback — should never reach here
        return self._do_handshake(text)

    def _do_handshake(self, text: str) -> SpiralOutput:
        """Name + mode selection."""
        text_lower = text.lower().strip()

        # detect mode from input
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

        # no biome detected — enter HOLD
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

        if mode == SessionMode.KID:
            # mirror energy, never identify
            if tone == "cautious":
                reply = "A plant that protects itself. Did you notice where it grows?"
            elif tone == "curious":
                reply = "Something caught your eye. What shape are the leaves?"
            elif tone == "excited":
                reply = "You found something! What does it feel like — rough, smooth, waxy?"
            else:
                reply = "Look closely. What do you notice first?"
        elif mode == SessionMode.CODER:
            reply = f"Biome: {self.state.context.T.biome or 'unknown'}. Observation logged."
        else:
            if tone == "cautious":
                reply = "Something with defences. Notice the habitat — that's the first clue."
            elif tone == "curious":
                reply = "Good eye. Leaf shape and arrangement tell you a lot."
            else:
                reply = "Observe the growth pattern. Where does it sit relative to light and water?"

        self.state.spiral = SpiralState.RITUAL
        return SpiralOutput(
            text=reply,
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

        # loop back to RENDER (not HANDSHAKE — session persists)
        self.state.spiral = SpiralState.RENDER

        return SpiralOutput(
            text=question,
            state_name=SpiralState.RENDER.value,
            breath=self.state.breath.value,
            anchor=anchor,
            ritual_question=question,
            weather=self.get_weather(),
        )
