"""
Bias Drift / Anti-Idolization Tracker.

Monitors three risks:
  1. Parasocial attachment — is the user becoming dependent on the system?
  2. Echo chamber — are inputs becoming repetitive loops?
  3. Obsession — is attention narrowing rather than expanding?

When drift exceeds thresholds, the engine injects sideways content
and grounding nudges instead of bans.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class DriftState:
    """Tracks bias drift indicators over a session."""
    parasocial_score: float = 0.0     # 0-1, how attached to the system
    echo_score: float = 0.0           # 0-1, how repetitive the loop
    narrowing_score: float = 0.0      # 0-1, how fixated attention is
    nudge_count: int = 0              # how many nudges issued this session
    last_nudge_tick: int = 0


@dataclass
class DriftNudge:
    """A sideways intervention to break drift."""
    kind: str       # "humor", "mundane", "reflective", "redirect"
    text: str


# Nudge pools — injected humor, mundane observations, reflective prompts
_HUMOR_NUDGES = [
    "A beetle just fell off a leaf. It seems fine.",
    "Somewhere, a crow is absolutely furious about something.",
    "The wind changed direction. The moss doesn't care.",
]

_MUNDANE_NUDGES = [
    "Your shoes are touching the ground.",
    "The sky is still there.",
    "Something nearby is making a sound you haven't named.",
]

_REFLECTIVE_NUDGES = [
    "What were you thinking about before you came here?",
    "If you could show this to someone, who would it be?",
    "What's the last thing you ate?",
]

_REDIRECT_NUDGES = [
    "Turn around. What's behind you?",
    "Look up. What's the highest thing you can see?",
    "Find something with a smell.",
]


# Dependency keywords — signs of parasocial attachment
_DEPENDENCY_SIGNALS = [
    "i need you", "don't leave", "you understand me", "only you",
    "stay", "help me", "you're the only", "i love you", "my friend",
    "talk to me", "are you there", "miss you",
]


class DriftTracker:
    """
    Monitors session for bias drift and emits nudges when needed.
    """

    PARASOCIAL_THRESHOLD = 0.5
    ECHO_THRESHOLD = 0.6
    NARROWING_THRESHOLD = 0.6
    COOLDOWN_TICKS = 5  # minimum ticks between nudges

    def __init__(self):
        self.state = DriftState()
        self._nudge_cycle = 0
        self._topic_history: deque = deque(maxlen=10)

    def update(self, text: str, repetition_score: float, tick: int,
               tone: Optional[str] = None) -> Optional[DriftNudge]:
        """
        Update drift scores and return a nudge if warranted.
        """
        self._update_parasocial(text)
        self._update_echo(repetition_score)
        self._update_narrowing(text, tone)

        # check if any threshold is exceeded
        if tick - self.state.last_nudge_tick < self.COOLDOWN_TICKS:
            return None

        nudge = None
        if self.state.parasocial_score > self.PARASOCIAL_THRESHOLD:
            nudge = self._pick_nudge("mundane")
        elif self.state.echo_score > self.ECHO_THRESHOLD:
            nudge = self._pick_nudge("redirect")
        elif self.state.narrowing_score > self.NARROWING_THRESHOLD:
            nudge = self._pick_nudge("humor")

        if nudge:
            self.state.nudge_count += 1
            self.state.last_nudge_tick = tick
            # decay scores after nudge
            self.state.parasocial_score *= 0.7
            self.state.echo_score *= 0.7
            self.state.narrowing_score *= 0.7

        return nudge

    def _update_parasocial(self, text: str):
        text_lower = text.lower()
        hits = sum(1 for sig in _DEPENDENCY_SIGNALS if sig in text_lower)
        if hits > 0:
            self.state.parasocial_score = min(1.0, self.state.parasocial_score + hits * 0.15)
        else:
            self.state.parasocial_score = max(0.0, self.state.parasocial_score - 0.03)

    def _update_echo(self, repetition_score: float):
        # echo tracks repetition over time
        self.state.echo_score = self.state.echo_score * 0.7 + repetition_score * 0.3

    def _update_narrowing(self, text: str, tone: Optional[str]):
        # track topic variety — are we seeing new words or the same ones?
        words = set(text.lower().split())
        if self._topic_history:
            recent_words = set()
            for prev in self._topic_history:
                recent_words.update(prev)
            if words and recent_words:
                novelty = len(words - recent_words) / max(len(words), 1)
                # low novelty = narrowing
                self.state.narrowing_score = (
                    self.state.narrowing_score * 0.8 + (1.0 - novelty) * 0.2
                )
        self._topic_history.append(words)

    def _pick_nudge(self, kind: str) -> DriftNudge:
        pools = {
            "humor": _HUMOR_NUDGES,
            "mundane": _MUNDANE_NUDGES,
            "reflective": _REFLECTIVE_NUDGES,
            "redirect": _REDIRECT_NUDGES,
        }
        pool = pools.get(kind, _MUNDANE_NUDGES)
        text = pool[self._nudge_cycle % len(pool)]
        self._nudge_cycle += 1
        return DriftNudge(kind=kind, text=text)

    def get_hud(self) -> dict:
        """Return the drift HUD for monitoring."""
        return {
            "parasocial": round(self.state.parasocial_score, 2),
            "echo": round(self.state.echo_score, 2),
            "narrowing": round(self.state.narrowing_score, 2),
            "nudge_count": self.state.nudge_count,
        }
