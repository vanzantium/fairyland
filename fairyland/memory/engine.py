"""
Memory Engine — compression, not storage.

Raw history is burned. Only compressed tattoos survive.
Friction logging captures moments of high pressure or hesitation.
The nightly dwell cycle synthesizes patterns and extracts stable rules.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class MemoryArtifact:
    """A single friction-logged moment."""
    timestamp: float
    pressure: float
    hesitation: str  # "NONE", "MILD", "STRONG"
    summary: str
    tick: int = 0


@dataclass
class MemoryEngineState:
    """Tracks daily artifacts, code tattoos, and scar signature."""
    daily_artifacts: List[MemoryArtifact] = field(default_factory=list)
    code_tattoos: List[str] = field(default_factory=list)
    scar_signature: float = 0.0


class MemoryEngine:
    """
    Friction logging + nightly dwell cycle.

    Only records moments where pressure > 0.6 or hesitation != NONE.
    Tattoos are stored as small text files; raw history is burned.
    """

    PRESSURE_THRESHOLD = 0.6

    def __init__(self, tattoo_dir: Optional[str] = None):
        self.state = MemoryEngineState()
        self.tattoo_dir = Path(tattoo_dir) if tattoo_dir else None
        if self.tattoo_dir:
            self.tattoo_dir.mkdir(parents=True, exist_ok=True)
            self._load_tattoos()

    def _load_tattoos(self):
        """Load existing tattoos from disk."""
        if not self.tattoo_dir:
            return
        for f in sorted(self.tattoo_dir.glob("*.tattoo")):
            self.state.code_tattoos.append(f.read_text().strip())

    # -- friction logging ---------------------------------------------------

    def log(self, pressure: float, hesitation: str, summary: str, tick: int = 0):
        """Record a friction moment if thresholds are met."""
        if pressure < self.PRESSURE_THRESHOLD and hesitation == "NONE":
            return  # below threshold — nothing to record
        artifact = MemoryArtifact(
            timestamp=time.time(),
            pressure=pressure,
            hesitation=hesitation,
            summary=summary,
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
        """
        artifacts = self.state.daily_artifacts
        if not artifacts:
            return None

        # 1. generative pass (simulated — high variance summary)
        dream = self._generate_dream_pass(artifacts)

        # 2. extraction pass (low variance — single rule)
        tattoo = self._extract_tattoo(dream, artifacts)

        # 3. update state
        self.state.code_tattoos.append(tattoo)
        self.state.scar_signature = min(1.0, self.state.scar_signature + 0.01 * len(artifacts))
        self.state.daily_artifacts = []  # burn raw history

        # persist tattoo to disk
        if self.tattoo_dir:
            idx = len(list(self.tattoo_dir.glob("*.tattoo")))
            path = self.tattoo_dir / f"{idx:04d}.tattoo"
            path.write_text(tattoo)

        return tattoo

    def _generate_dream_pass(self, artifacts: List[MemoryArtifact]) -> str:
        """Generative pass: summarize the day's friction at high variance."""
        count = len(artifacts)
        avg_pressure = sum(a.pressure for a in artifacts) / max(count, 1)
        max_pressure = max(a.pressure for a in artifacts)
        hesitations = [a for a in artifacts if a.hesitation != "NONE"]

        if avg_pressure > 0.80:
            return "System endured extreme load and held partial coherence."
        elif avg_pressure > 0.60:
            return f"Moderate friction across {count} moments. {len(hesitations)} hesitations."
        elif hesitations:
            return f"Low pressure but {len(hesitations)} hesitation(s) surfaced."
        else:
            return f"Quiet day. {count} friction events at low intensity."

    def _extract_tattoo(self, dream: str, artifacts: List[MemoryArtifact]) -> str:
        """Extraction pass: compress dream into one stable rule."""
        # find the highest-pressure artifact
        peak = max(artifacts, key=lambda a: a.pressure)
        return f"[scar={self.state.scar_signature:.2f}] {dream} Peak: {peak.summary}"

    # -- session burn -------------------------------------------------------

    def burn_session(self):
        """Eat session memory. Only tattoos survive."""
        self.state.daily_artifacts = []
