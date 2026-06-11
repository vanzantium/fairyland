"""
Rhythm sensing — touch telemetry instead of text.

The kids-mode canvas sends no words. It sends marks: timestamped touch
strokes with position and length. This module compresses a batch of marks
into the same signal shape the Spiral Engine already regulates on
(``TextSignals``), so the kernel/breath/oscillator pipeline runs unchanged.

The mapping, in spec terms (Fairyland v14):
  - rapid repetitive marking  -> staccato rhythm + repetition -> pressure rises
  - slow exploratory marking  -> flowing rhythm + spread      -> pressure settles
  - stillness                 -> silence ratio                -> calm

No content is read. No image is stored. Only rhythm.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence

from .sensing import TextSignals


@dataclass
class Mark:
    """One touch stroke, as reported by the canvas client.

    t        — client timestamp in milliseconds (monotonic within a session)
    x, y     — normalised stroke start position (0..1 of viewport)
    length   — stroke path length, normalised to viewport diagonal (0..~2)
    duration — stroke duration in milliseconds
    """
    t: float
    x: float
    y: float
    length: float = 0.0
    duration: float = 0.0


def _parse_marks(raw: Sequence[dict]) -> List[Mark]:
    marks: List[Mark] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        try:
            marks.append(Mark(
                t=float(item.get("t", 0)),
                x=max(0.0, min(1.0, float(item.get("x", 0.5)))),
                y=max(0.0, min(1.0, float(item.get("y", 0.5)))),
                length=max(0.0, min(2.0, float(item.get("len", 0)))),
                duration=max(0.0, float(item.get("dur", 0))),
            ))
        except (TypeError, ValueError):
            continue
    marks.sort(key=lambda m: m.t)
    return marks


def _cadence(marks: List[Mark], window_s: float) -> float:
    """Marks per second across the batch window."""
    if not marks or window_s <= 0:
        return 0.0
    return len(marks) / window_s


def _spatial_spread(marks: List[Mark]) -> float:
    """How much of the canvas the marks explore (0 = one spot, 1 = everywhere).

    Counts visited cells of a coarse 6x6 grid relative to the number of
    marks — the analogue of vocabulary density for touch.
    """
    if not marks:
        return 0.0
    cells = {(min(5, int(m.x * 6)), min(5, int(m.y * 6))) for m in marks}
    return min(1.0, len(cells) / max(1.0, min(len(marks), 36) * 0.5))


def _repetition(marks: List[Mark]) -> float:
    """Looping in place: consecutive marks landing near each other with
    similar stroke lengths score high. The analogue of repeated phrases."""
    if len(marks) < 3:
        return 0.0
    near = 0
    similar = 0
    pairs = 0
    for prev, cur in zip(marks, marks[1:]):
        pairs += 1
        dist = math.hypot(cur.x - prev.x, cur.y - prev.y)
        if dist < 0.12:
            near += 1
        if abs(cur.length - prev.length) < 0.05:
            similar += 1
    return min(1.0, (near / pairs) * 0.65 + (similar / pairs) * 0.35)


def _trajectory(marks: List[Mark]) -> str:
    """Is the marking speeding up or settling across the batch?"""
    if len(marks) < 4:
        return "flat"
    mid = len(marks) // 2
    first, second = marks[:mid], marks[mid:]

    def _rate(chunk: List[Mark]) -> float:
        span = (chunk[-1].t - chunk[0].t) / 1000.0
        return len(chunk) / span if span > 0.2 else float(len(chunk))

    early, late = _rate(first), _rate(second)
    if late > early * 1.4:
        return "escalating"
    if late < early * 0.6:
        return "settling"
    return "flat"


def _silence_ratio(marks: List[Mark], window_s: float) -> float:
    """Fraction of the window spent in gaps longer than 3 seconds."""
    if window_s <= 0:
        return 1.0
    if not marks:
        return 1.0
    quiet = 0.0
    times = [m.t / 1000.0 for m in marks]
    gaps = [b - a for a, b in zip(times, times[1:])]
    quiet = sum(g for g in gaps if g > 3.0)
    return max(0.0, min(1.0, quiet / window_s))


def extract_rhythm_signals(raw_marks: Sequence[dict],
                           window_s: float = 2.5) -> TextSignals:
    """Compress one telemetry batch into TextSignals.

    An empty batch is a valid signal: stillness. It reads as flowing,
    settling, fully silent — which lets the kernel's pressure decay.
    """
    marks = _parse_marks(raw_marks)

    if marks and len(marks) >= 2:
        span = (marks[-1].t - marks[0].t) / 1000.0
        window_s = max(window_s, span)

    cadence = _cadence(marks, window_s)
    repetition = _repetition(marks)
    spread = _spatial_spread(marks)
    trajectory = _trajectory(marks)
    silence = _silence_ratio(marks, window_s)

    if not marks:
        rhythm = "flowing"
        trajectory = "settling"
    elif cadence >= 2.5:
        rhythm = "staccato"
    elif cadence <= 0.8:
        rhythm = "flowing"
    else:
        rhythm = "mixed"

    return TextSignals(
        tone=None,                      # no words, no labels
        rhythm=rhythm,
        word_density=spread,            # exploration is the density analogue
        repetition_score=repetition,
        emotional_direction=trajectory,
        sentence_count=len(marks),
        avg_word_length=sum(m.length for m in marks) / len(marks) if marks else 0.0,
        has_question=False,
        has_exclamation=False,
        silence_ratio=silence,
        burst_score=min(1.0, cadence / 5.0),  # ~5 marks/s = full intensity
    )
