"""
Sensing — richer signal extraction from user input.

Goes beyond keyword matching to detect:
  - Sentence rhythm (short bursts vs flowing)
  - Repetition patterns (loops vs exploration)
  - Emotional trajectory (escalating vs settling)
  - Vocabulary density (sparse vs rich)

No ML dependencies. Pure text analysis.
"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class TextSignals:
    """Extracted signals from a single input."""
    tone: Optional[str]
    rhythm: str            # "staccato", "flowing", "mixed"
    word_density: float    # unique words / total words
    repetition_score: float  # 0-1, how much this repeats recent inputs
    emotional_direction: str  # "escalating", "settling", "flat"
    sentence_count: int
    avg_word_length: float
    has_question: bool
    has_exclamation: bool
    silence_ratio: float   # fraction of very short sentences (< 3 words)


# ---------------------------------------------------------------------------
# Tone detection — richer than keyword matching
# ---------------------------------------------------------------------------

_TONE_PATTERNS = {
    "curious": {
        "keywords": ["what", "how", "why", "tell me", "wonder", "where", "which", "who"],
        "patterns": [r"\?$", r"^(is|are|do|does|can|could|would)\b"],
        "weight": 1.0,
    },
    "confused": {
        "keywords": ["don't understand", "huh", "what do you mean", "confused", "lost", "wait"],
        "patterns": [r"\?\s*\?", r"^(but|wait)\b"],
        "weight": 1.2,
    },
    "excited": {
        "keywords": ["wow", "cool", "amazing", "awesome", "beautiful", "incredible", "look"],
        "patterns": [r"!{2,}", r"^(oh|wow|yes)\b"],
        "weight": 1.0,
    },
    "cautious": {
        "keywords": ["careful", "sting", "hurt", "sharp", "danger", "scary", "poison",
                     "thorn", "prickly", "bite", "burn"],
        "patterns": [r"(ouch|ow|yikes)"],
        "weight": 1.3,
    },
    "calm": {
        "keywords": ["nice", "pretty", "peaceful", "soft", "gentle", "quiet", "still",
                     "lovely", "sweet", "warm"],
        "patterns": [r"\.{3}", r"^(mmm|ahh|hmm)\b"],
        "weight": 0.9,
    },
    "withdrawn": {
        "keywords": ["ok", "fine", "whatever", "idk", "dunno", "meh", "sure"],
        "patterns": [r"^.{1,4}$"],
        "weight": 1.1,
    },
}


def detect_tone(text: str) -> Optional[str]:
    """Detect emotional tone from text using keywords + regex patterns."""
    text_lower = text.lower().strip()
    scores: dict[str, float] = {}

    for tone, config in _TONE_PATTERNS.items():
        score = 0.0
        for kw in config["keywords"]:
            if kw in text_lower:
                score += 1.0
        for pat in config["patterns"]:
            if re.search(pat, text_lower, re.MULTILINE):
                score += 0.5
        scores[tone] = score * config["weight"]

    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else None


# ---------------------------------------------------------------------------
# Rhythm analysis
# ---------------------------------------------------------------------------

def _split_sentences(text: str) -> List[str]:
    """Split text into sentences."""
    parts = re.split(r'[.!?]+', text)
    return [s.strip() for s in parts if s.strip()]


def detect_rhythm(text: str) -> str:
    """Classify input rhythm: staccato (short bursts), flowing (long), or mixed."""
    sentences = _split_sentences(text)
    if not sentences:
        return "staccato"
    lengths = [len(s.split()) for s in sentences]
    avg = sum(lengths) / len(lengths)
    if avg <= 3:
        return "staccato"
    elif avg >= 8:
        return "flowing"
    return "mixed"


def compute_word_density(text: str) -> float:
    """Ratio of unique words to total words. High = varied vocabulary."""
    words = text.lower().split()
    if not words:
        return 0.0
    return len(set(words)) / len(words)


# ---------------------------------------------------------------------------
# Repetition detection
# ---------------------------------------------------------------------------

def compute_repetition(text: str, history: deque) -> float:
    """
    Score 0-1 indicating how much this input repeats recent history.
    Uses word overlap with last 5 inputs.
    """
    current_words = set(text.lower().split())
    if not current_words or not history:
        return 0.0

    overlaps = []
    recent = list(history)[-5:]
    for entry in recent:
        prev_text = entry.get("input", "") if isinstance(entry, dict) else str(entry)
        prev_words = set(prev_text.lower().split())
        if prev_words:
            overlap = len(current_words & prev_words) / max(len(current_words | prev_words), 1)
            overlaps.append(overlap)

    return sum(overlaps) / max(len(overlaps), 1)


# ---------------------------------------------------------------------------
# Emotional trajectory
# ---------------------------------------------------------------------------

_ESCALATION_WORDS = {"help", "please", "stop", "more", "again", "need", "want", "now", "!"}
_SETTLING_WORDS = {"ok", "thanks", "good", "fine", "nice", "yes", "hmm", "ah", "oh"}


def detect_trajectory(text: str, history: deque) -> str:
    """
    Detect whether emotion is escalating, settling, or flat.
    Uses current input + recent history pressure trend.
    """
    words = set(text.lower().split())
    esc_score = len(words & _ESCALATION_WORDS)
    set_score = len(words & _SETTLING_WORDS)

    # check if recent history shows increasing intensity
    recent = list(history)[-3:]
    if len(recent) >= 2:
        prev_lengths = [len(str(e.get("input", "")).split()) if isinstance(e, dict) else 0
                        for e in recent]
        current_length = len(text.split())
        if current_length > max(prev_lengths, default=0) * 1.5:
            esc_score += 1

    if esc_score > set_score:
        return "escalating"
    elif set_score > esc_score:
        return "settling"
    return "flat"


# ---------------------------------------------------------------------------
# Full signal extraction
# ---------------------------------------------------------------------------

def extract_signals(text: str, history: deque) -> TextSignals:
    """Extract all signals from user input."""
    sentences = _split_sentences(text)
    words = text.split()
    avg_word_len = sum(len(w) for w in words) / max(len(words), 1)
    short_sentences = sum(1 for s in sentences if len(s.split()) < 3)
    silence_ratio = short_sentences / max(len(sentences), 1)

    return TextSignals(
        tone=detect_tone(text),
        rhythm=detect_rhythm(text),
        word_density=compute_word_density(text),
        repetition_score=compute_repetition(text, history),
        emotional_direction=detect_trajectory(text, history),
        sentence_count=len(sentences),
        avg_word_length=avg_word_len,
        has_question="?" in text,
        has_exclamation="!" in text,
        silence_ratio=silence_ratio,
    )
