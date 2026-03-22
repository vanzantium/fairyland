"""
Memory Engine — compression, not storage.

Raw history is burned. Only compressed tattoos survive.
Friction logging captures moments of high pressure or hesitation.
The nightly dwell cycle synthesizes patterns and extracts stable rules.
Tattoos feed back into engine behavior on session start.
"""

from __future__ import annotations

import os
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class MemoryArtifact:
    """A single friction-logged moment."""
    timestamp: float
    pressure: float
    hesitation: str  # "NONE", "MILD", "STRONG"
    summary: str
    tone: Optional[str] = None
    rhythm: Optional[str] = None
    tick: int = 0


@dataclass
class MemoryEngineState:
    """Tracks daily artifacts, code tattoos, and scar signature."""
    daily_artifacts: List[MemoryArtifact] = field(default_factory=list)
    code_tattoos: List[str] = field(default_factory=list)
    scar_signature: float = 0.0
    patterns: Dict[str, float] = field(default_factory=dict)


class MemoryEngine:
    """
    Friction logging + nightly dwell cycle.

    Only records moments where pressure > 0.6 or hesitation != NONE.
    Tattoos are stored as small text files; raw history is burned.
    Patterns extracted from tattoos feed back into engine behavior.
    """

    PRESSURE_THRESHOLD = 0.6

    def __init__(self, tattoo_dir: Optional[str] = None):
        self.state = MemoryEngineState()
        self.tattoo_dir = Path(tattoo_dir) if tattoo_dir else None
        if self.tattoo_dir:
            self.tattoo_dir.mkdir(parents=True, exist_ok=True)
            self._load_tattoos()
            self._extract_patterns()

    def _load_tattoos(self):
        """Load existing tattoos from disk."""
        if not self.tattoo_dir:
            return
        for f in sorted(self.tattoo_dir.glob("*.tattoo")):
            self.state.code_tattoos.append(f.read_text().strip())

    def _extract_patterns(self):
        """Extract recurring patterns from accumulated tattoos."""
        if not self.state.code_tattoos:
            return
        self.state.patterns = analyze_tattoo_patterns(self.state.code_tattoos)

    # -- friction logging ---------------------------------------------------

    def log(self, pressure: float, hesitation: str, summary: str,
            tick: int = 0, tone: Optional[str] = None,
            rhythm: Optional[str] = None):
        """Record a friction moment if thresholds are met."""
        if pressure < self.PRESSURE_THRESHOLD and hesitation == "NONE":
            return  # below threshold — nothing to record
        artifact = MemoryArtifact(
            timestamp=time.time(),
            pressure=pressure,
            hesitation=hesitation,
            summary=summary,
            tone=tone,
            rhythm=rhythm,
            tick=tick,
        )
        self.state.daily_artifacts.append(artifact)

    # -- nightly dwell cycle ------------------------------------------------

    def dwell(self) -> Optional[str]:
        """
        Run the nightly dwell cycle.

        1. Generative pass — synthesize patterns from daily artifacts.
        2. Extraction pass — reduce to a single stable rule (tattoo).
        3. Update: append tattoo, clear artifacts, increase scar.
        4. Re-extract patterns from all tattoos.
        """
        artifacts = self.state.daily_artifacts
        if not artifacts:
            return None

        # 1. generative pass (high variance — synthesize across artifacts)
        dream = self._generate_dream_pass(artifacts)

        # 2. extraction pass (low variance — single rule)
        tattoo = self._extract_tattoo(dream, artifacts)

        # 3. update state
        self.state.code_tattoos.append(tattoo)
        self.state.scar_signature = min(1.0, self.state.scar_signature + 0.01 * len(artifacts))
        self.state.daily_artifacts = []  # burn raw history

        # 4. re-extract patterns from all tattoos
        self._extract_patterns()

        # persist tattoo to disk
        if self.tattoo_dir:
            idx = len(list(self.tattoo_dir.glob("*.tattoo")))
            path = self.tattoo_dir / f"{idx:04d}.tattoo"
            path.write_text(tattoo)

        return tattoo

    def _generate_dream_pass(self, artifacts: List[MemoryArtifact]) -> str:
        """
        Generative pass: synthesize across artifacts at high variance.

        Looks for:
          - Pressure trajectory (rising, falling, spikes)
          - Hesitation clustering (early, late, throughout)
          - Tone patterns (what tone co-occurs with high pressure)
          - Rhythm shifts (did input rhythm change during friction?)
        """
        count = len(artifacts)
        avg_pressure = sum(a.pressure for a in artifacts) / max(count, 1)
        hesitations = [a for a in artifacts if a.hesitation != "NONE"]

        # pressure trajectory
        if count >= 3:
            first_half = artifacts[:count // 2]
            second_half = artifacts[count // 2:]
            p1 = sum(a.pressure for a in first_half) / len(first_half)
            p2 = sum(a.pressure for a in second_half) / len(second_half)
            if p2 > p1 + 0.15:
                trajectory = "Pressure rose through the session."
            elif p1 > p2 + 0.15:
                trajectory = "Pressure settled as session progressed."
            else:
                trajectory = "Pressure held steady."
        else:
            trajectory = "Brief encounter."

        # tone co-occurrence with friction
        tone_counts = Counter(a.tone for a in artifacts if a.tone)
        dominant_tone = tone_counts.most_common(1)[0][0] if tone_counts else "unknown"

        # hesitation clustering
        if hesitations:
            hes_ticks = [a.tick for a in hesitations]
            avg_hes_tick = sum(hes_ticks) / len(hes_ticks)
            all_ticks = [a.tick for a in artifacts]
            mid_tick = sum(all_ticks) / len(all_ticks)
            if avg_hes_tick < mid_tick - 1:
                hes_pattern = "Hesitation clustered early."
            elif avg_hes_tick > mid_tick + 1:
                hes_pattern = "Hesitation emerged late."
            else:
                hes_pattern = "Hesitation was distributed."
        else:
            hes_pattern = "No hesitation."

        if avg_pressure > 0.80:
            base = "System endured extreme load and held partial coherence."
        elif avg_pressure > 0.60:
            base = f"Moderate friction across {count} moments."
        elif hesitations:
            base = f"Low pressure but {len(hesitations)} hesitation(s) surfaced."
        else:
            base = f"Quiet session. {count} friction events at low intensity."

        return f"{base} {trajectory} Dominant tone: {dominant_tone}. {hes_pattern}"

    def _extract_tattoo(self, dream: str, artifacts: List[MemoryArtifact]) -> str:
        """Extraction pass: compress dream into one stable rule."""
        peak = max(artifacts, key=lambda a: a.pressure)
        # include rhythm if available
        rhythm_note = f" Rhythm: {peak.rhythm}." if peak.rhythm else ""
        return f"[scar={self.state.scar_signature:.2f}] {dream}{rhythm_note} Peak: {peak.summary}"

    # -- pattern analysis ---------------------------------------------------

    def get_pressure_baseline(self) -> float:
        """Return a baseline pressure adjustment based on tattoo patterns."""
        return self.state.patterns.get("pressure_baseline", 0.0)

    def get_dominant_tone(self) -> Optional[str]:
        """Return the historically dominant tone from tattoo patterns."""
        tone = self.state.patterns.get("dominant_tone_key", None)
        return tone

    # -- session burn -------------------------------------------------------

    def burn_session(self):
        """Eat session memory. Only tattoos survive."""
        self.state.daily_artifacts = []


# ---------------------------------------------------------------------------
# Tattoo pattern analysis (operates on accumulated tattoos)
# ---------------------------------------------------------------------------

def analyze_tattoo_patterns(tattoos: List[str]) -> Dict[str, float]:
    """
    Extract recurring patterns from a list of tattoo strings.

    Returns a dict of pattern signals that can feed back into engine behavior.
    """
    if not tattoos:
        return {}

    patterns: Dict[str, float] = {}

    # extract scar values
    scars = []
    for t in tattoos:
        m = re.search(r'\[scar=([\d.]+)\]', t)
        if m:
            scars.append(float(m.group(1)))

    if scars:
        patterns["avg_scar"] = sum(scars) / len(scars)
        patterns["max_scar"] = max(scars)
        # rising scars = system is accumulating friction over time
        if len(scars) >= 3 and scars[-1] > scars[0] + 0.05:
            patterns["scar_rising"] = 1.0
        else:
            patterns["scar_rising"] = 0.0

    # detect recurring tones
    tone_counts: Counter = Counter()
    for t in tattoos:
        m = re.search(r'Dominant tone: (\w+)', t)
        if m:
            tone_counts[m.group(1)] += 1
    if tone_counts:
        dominant = tone_counts.most_common(1)[0]
        patterns["dominant_tone_key"] = dominant[0]
        patterns["dominant_tone_freq"] = dominant[1] / len(tattoos)

    # detect pressure tendency
    extreme_count = sum(1 for t in tattoos if "extreme load" in t.lower())
    moderate_count = sum(1 for t in tattoos if "moderate friction" in t.lower())
    quiet_count = sum(1 for t in tattoos if "quiet" in t.lower())
    total = max(len(tattoos), 1)

    if extreme_count / total > 0.3:
        patterns["pressure_baseline"] = 0.1  # raise baseline — system runs hot
    elif quiet_count / total > 0.6:
        patterns["pressure_baseline"] = -0.05  # lower baseline — system runs cool
    else:
        patterns["pressure_baseline"] = 0.0

    # detect hesitation tendency
    hes_count = sum(1 for t in tattoos if "hesitation" in t.lower())
    patterns["hesitation_frequency"] = hes_count / total

    return patterns
