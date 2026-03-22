"""Tests for the rich sensing module."""

from collections import deque

from fairyland.engine.sensing import (
    compute_repetition,
    compute_word_density,
    detect_rhythm,
    detect_tone,
    detect_trajectory,
    extract_signals,
)


class TestToneDetection:
    def test_curious(self):
        assert detect_tone("What is this plant?") == "curious"

    def test_cautious(self):
        assert detect_tone("ouch that stings!") == "cautious"

    def test_excited(self):
        assert detect_tone("wow amazing!!") == "excited"

    def test_calm(self):
        assert detect_tone("pretty and peaceful") == "calm"

    def test_withdrawn(self):
        assert detect_tone("ok") == "withdrawn"

    def test_confused(self):
        assert detect_tone("huh what do you mean") == "confused"

    def test_none_for_neutral(self):
        assert detect_tone("the number is 42") is None


class TestRhythm:
    def test_staccato(self):
        assert detect_rhythm("Stop. Look. Wait.") == "staccato"

    def test_flowing(self):
        assert detect_rhythm(
            "I was walking through the forest and I noticed a beautiful fern "
            "growing near the edge of the stream where the light comes through"
        ) == "flowing"

    def test_mixed(self):
        assert detect_rhythm("I saw a plant. It was growing near the old wall by the road.") == "mixed"


class TestRepetition:
    def test_no_history(self):
        assert compute_repetition("hello", deque()) == 0.0

    def test_exact_repeat(self):
        history = deque([{"input": "hello world"}])
        score = compute_repetition("hello world", history)
        assert score > 0.5

    def test_novel_input(self):
        history = deque([{"input": "the forest is dark"}])
        score = compute_repetition("ocean waves crash", history)
        assert score < 0.3


class TestTrajectory:
    def test_escalating(self):
        history = deque([
            {"input": "hi"},
            {"input": "help"},
        ])
        assert detect_trajectory("please help me now!", history) == "escalating"

    def test_settling(self):
        history = deque([
            {"input": "what is happening"},
        ])
        assert detect_trajectory("ok thanks", history) == "settling"


class TestWordDensity:
    def test_high_density(self):
        d = compute_word_density("every single word here is completely unique and different")
        assert d > 0.8

    def test_low_density(self):
        d = compute_word_density("the the the the the")
        assert d < 0.3


class TestExtractSignals:
    def test_returns_all_fields(self):
        signals = extract_signals("What is this pretty flower?", deque())
        assert signals.tone is not None
        assert signals.rhythm in ("staccato", "flowing", "mixed")
        assert 0.0 <= signals.repetition_score <= 1.0
        assert signals.emotional_direction in ("escalating", "settling", "flat")
        assert signals.sentence_count >= 1
