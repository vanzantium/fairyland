"""
Proper Shuffle — patterned discovery, not random.

Uses the Golden Ratio offset to walk through a playlist in a way
that feels surprising but never clusters. Session-bound only.
Silence enforced every 3 tracks. After silence -> material anchor -> exit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

# Golden ratio conjugate — the offset that maximally avoids clustering
PHI = 0.6180339887498949


@dataclass
class Track:
    """A single track in the playlist."""
    id: str
    title: str
    duration_s: float = 180.0
    mood: str = "neutral"


@dataclass
class ShuffleState:
    """State for one shuffle session."""
    playlist: List[Track] = field(default_factory=list)
    cursor: float = 0.0       # position in [0, 1) space
    tracks_since_silence: int = 0
    total_played: int = 0
    in_silence: bool = False
    finished: bool = False


@dataclass
class ShuffleOutput:
    """What the shuffle emits."""
    track: Optional[Track]
    silence: bool = False
    anchor_cue: bool = False    # true = material anchor should appear after silence
    exit_cue: bool = False      # true = session should end after anchor


class ProperShuffle:
    """
    Golden Ratio shuffle with enforced silence.

    Every 3 tracks -> silence gap.
    After silence -> material anchor cue -> exit signal.
    No RNG. No recommendations. Just patterned discovery.
    """

    SILENCE_EVERY = 3

    def __init__(self, playlist: List[Track]):
        self.state = ShuffleState(playlist=list(playlist))
        if playlist:
            # start at a deterministic but non-obvious position
            self.state.cursor = PHI * 0.5  # offset start

    def next(self) -> ShuffleOutput:
        """Get the next shuffle output."""
        if not self.state.playlist:
            return ShuffleOutput(track=None, exit_cue=True)

        if self.state.finished:
            return ShuffleOutput(track=None, exit_cue=True)

        # silence check
        if self.state.tracks_since_silence >= self.SILENCE_EVERY:
            self.state.tracks_since_silence = 0
            self.state.in_silence = True
            return ShuffleOutput(track=None, silence=True, anchor_cue=True)

        # if we were in silence, next output triggers exit
        if self.state.in_silence:
            self.state.in_silence = False
            self.state.finished = True
            return ShuffleOutput(track=None, exit_cue=True)

        # golden ratio walk
        n = len(self.state.playlist)
        index = int(self.state.cursor * n) % n
        track = self.state.playlist[index]

        # advance cursor by golden ratio
        self.state.cursor = (self.state.cursor + PHI) % 1.0
        self.state.tracks_since_silence += 1
        self.state.total_played += 1

        return ShuffleOutput(track=track)

    def reset(self, playlist: Optional[List[Track]] = None):
        """Reset for a new session."""
        if playlist is not None:
            self.state.playlist = list(playlist)
        self.state.cursor = PHI * 0.5
        self.state.tracks_since_silence = 0
        self.state.total_played = 0
        self.state.in_silence = False
        self.state.finished = False
