"""
Listening — feel the music while it plays, form meaning after it stops.

Port of the Music Mode scaffold (brain: "Music mode 11/12") into the
Fairyland engine, threadless and beatless. The principle survives intact:

    The organism FEELS the music while it plays, but doesn't REMEMBER
    it until after it stops. Memory forms from the residual impression,
    not from the live experience. If you judge in real time, you build
    a music critic. If you let the thermal residue settle, you build
    something that experienced the song.

The client samples the playing audio (band energies + onsets, RM12's
mapping) and sends impression packets. They accumulate here WITHOUT
touching the kernel. When the spiral dealer reaches its enforced
silence, ``settle()`` runs once: the kernel wanders through the thermal
residue and shifts. The silence is the settle window.

Calibration doctrine (from the update doc): the household's own ears are
the reference standard. Play a song you love and a song you hate — if
the residue reads the same, the thresholds are noise; if they differ
predictably, they're set right.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence

from .state import KernelState


@dataclass
class Impression:
    """One sampled moment of musical feeling — an impression, not a memory.

    t         — client timestamp ms
    low/mid/high — normalised band energies (0..1)
    amplitude — overall loudness (0..1)
    onset     — transient detected this sample
    """
    t: float
    low: float = 0.0
    mid: float = 0.0
    high: float = 0.0
    amplitude: float = 0.0
    onset: bool = False


def _parse_packets(raw: Sequence[dict]) -> List[Impression]:
    out: List[Impression] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        try:
            out.append(Impression(
                t=float(item.get("t", 0)),
                low=max(0.0, min(1.0, float(item.get("low", 0)))),
                mid=max(0.0, min(1.0, float(item.get("mid", 0)))),
                high=max(0.0, min(1.0, float(item.get("high", 0)))),
                amplitude=max(0.0, min(1.0, float(item.get("amp", 0)))),
                onset=bool(item.get("onset", False)),
            ))
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda i: i.t)
    return out


class ListeningBuffer:
    """Accumulates impressions during playback. Touches nothing.

    KEY PRINCIPLE (verbatim from the scaffold): nothing in this buffer
    triggers kernel updates or memory formation. The organism feels the
    music but doesn't process it. Processing happens in settle().
    """

    MAX_IMPRESSIONS = 4000  # ~4½ min at 15 Hz; old impressions fade first

    def __init__(self):
        self.impressions: List[Impression] = []

    def feel(self, packets: Sequence[dict]) -> int:
        """Absorb a batch of impression packets. Returns how many landed."""
        parsed = _parse_packets(packets)
        self.impressions.extend(parsed)
        if len(self.impressions) > self.MAX_IMPRESSIONS:
            self.impressions = self.impressions[-self.MAX_IMPRESSIONS:]
        return len(parsed)

    def clear(self) -> None:
        """The impression fades."""
        self.impressions.clear()

    # -- the thermal residue --------------------------------------------------

    def residue(self) -> Dict[str, float]:
        """The shape left behind after the music stops. Not a memory —
        the warmth left on a seat after someone stands up."""
        imps = self.impressions
        n = len(imps)
        if n == 0:
            return {
                "warmth": 0.0, "weight": 0.0, "surprise": 0.0,
                "groove": 0.0, "tension": 0.0, "swing_ratio": 0.5,
                "density": 0.0, "impressions": 0,
            }

        # warmth: low-band dominance (bass = warm, treble = cool)
        total_energy = sum(i.low + i.mid + i.high for i in imps) or 1e-9
        warmth = sum(i.low for i in imps) / total_energy

        # weight: average loudness
        weight = sum(i.amplitude for i in imps) / n

        # onsets and their spacing
        onset_times = [i.t / 1000.0 for i in imps if i.onset]
        surprise = 0.0
        groove = 0.0
        tension = 0.0
        if len(onset_times) >= 3:
            gaps = [b - a for a, b in zip(onset_times, onset_times[1:])]
            gaps = [g for g in gaps if 0.0 < g < 5.0]
            if gaps:
                mean_gap = sum(gaps) / len(gaps)
                var = sum((g - mean_gap) ** 2 for g in gaps) / len(gaps)
                # regular onsets = groove; erratic onsets = tension
                # (beatless analogue of on-beat/off-beat groove_pull)
                regularity = max(0.0, 1.0 - (var / max(mean_gap ** 2, 1e-9)))
                groove = regularity * min(1.0, len(gaps) / 30.0) * 3.0
                tension = (1.0 - regularity) * min(1.0, len(gaps) / 30.0) * 3.0
                # surprise: onsets arriving after long quiet
                surprise = sum(min(1.0, g * 0.5) for g in gaps if g > 1.5)

        swing = groove / max(groove + tension, 1e-9) if (groove + tension) > 0 else 0.5

        span = (imps[-1].t - imps[0].t) / 1000.0
        density = n / max(span, 1e-9) if span > 0 else 0.0

        return {
            "warmth": round(warmth, 3),
            "weight": round(weight, 3),
            "surprise": round(surprise, 3),
            "groove": round(groove, 3),
            "tension": round(tension, 3),
            "swing_ratio": round(swing, 3),
            "density": round(density, 3),
            "impressions": n,
        }


def settle(kernel: KernelState, residue: Dict[str, float]) -> Dict[str, Any]:
    """Let meaning form from the thermal residue. One pass, after the music.

    The mapping follows the Music Mode scaffold, adapted to Fairyland's
    kernel (which has no surprise_load — surprise lands on temperature
    and stress instead). The memory of the song isn't the notes — it's
    how the kernel changed because of the thermal impression.
    """
    warmth = residue.get("warmth", 0.0)
    weight = residue.get("weight", 0.0)
    swing = residue.get("swing_ratio", 0.5)
    tension = residue.get("tension", 0.0)
    surprise = residue.get("surprise", 0.0)
    density = residue.get("density", 0.0)

    before = {
        "temperature": kernel.temperature, "pressure": kernel.pressure,
        "groove": kernel.groove, "coherence": kernel.coherence,
    }

    if residue.get("impressions", 0) > 0:
        # warmth -> temperature (bass-heavy music leaves a warm organism)
        kernel.temperature = kernel.temperature * 0.7 + warmth * 0.3

        # weight -> pressure (loud = heavy)
        kernel.pressure = min(1.0, kernel.pressure * 0.8 + weight * 0.2)

        # high swing: the music resolved its tensions well
        if swing > 0.6:
            kernel.groove = min(1.0, kernel.groove + swing * 0.15)
            kernel.coherence = min(1.0, kernel.coherence + 0.05)
        # low swing with real tension: unresolved (interesting but unsettling)
        elif swing < 0.3 and tension > 1.0:
            kernel.pressure = min(1.0, kernel.pressure + 0.05)
            kernel.stress = min(1.0, kernel.stress + 0.05)

        # surprise raises temperature a touch (novelty), too much adds stress
        if surprise > 2.0:
            kernel.stress = min(1.0, kernel.stress + surprise * 0.02)
        elif surprise > 0.5:
            kernel.temperature = min(1.0, kernel.temperature + 0.04)

        # dense fast music costs reserve
        if density > 10:
            kernel.reserve = max(0.0, kernel.reserve - 0.02)

        # restorative when groovy and warm
        if swing > 0.5 and warmth > 0.4:
            kernel.recovery = min(1.0, kernel.recovery + 0.04)

    return {
        "settled": True,
        "residue": residue,
        "shift": {
            k: round(getattr(kernel, k) - v, 3) for k, v in before.items()
        },
    }
