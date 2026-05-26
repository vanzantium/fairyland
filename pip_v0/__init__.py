"""
PipV0 — weekly batch compression engine.

Detects phone/PC usage friction patterns, compresses them through
a three-tier biomimetic memory (fur/skin/tattoo), and emits proposals.
"""

from .pip_engine import PipEngine, MemoryState, ThermalState, Tattoo, ProposalCard
from .pip_token_guard import assess_interaction, record_event, status as token_status

__all__ = [
    "PipEngine",
    "MemoryState",
    "ThermalState",
    "Tattoo",
    "ProposalCard",
    "assess_interaction",
    "record_event",
    "token_status",
]
