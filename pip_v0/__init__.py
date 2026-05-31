"""
PipV0 — weekly batch compression engine + text bridge agent.

Detects phone/PC usage friction patterns, compresses them through
a three-tier biomimetic memory (fur/skin/tattoo), and emits proposals.

The text bridge lets Pip type into external tools (Claude Code, Codex, etc.)
and harvest their responses via clipboard — no API keys needed.
"""

from .pip_engine import PipEngine, MemoryState, ThermalState, Tattoo, ProposalCard
from .pip_token_guard import assess_interaction, record_event, status as token_status
from . import pip_text_bridge as bridge
from . import pip_personas as personas
from . import pip_bridge_jobs as bridge_jobs
from . import pip_self_improve as self_improve
from . import pip_sentinel as sentinel

__all__ = [
    "PipEngine",
    "MemoryState",
    "ThermalState",
    "Tattoo",
    "ProposalCard",
    "assess_interaction",
    "record_event",
    "token_status",
    "bridge",
    "personas",
    "bridge_jobs",
    "self_improve",
    "sentinel",
]
