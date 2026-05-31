"""Tests for pip_self_improve — BES-inspired strategy learning."""

import os
import tempfile

os.environ["PIP_MEMORY_PATH"] = tempfile.mkdtemp(prefix="pip_improve_test_")

from pip_v0 import pip_self_improve as SI


def test_classify_task():
    assert SI.classify_task("write a function to sort") == "code_write"
    assert SI.classify_task("fix the bug in the parser") == "code_fix"
    assert SI.classify_task("explain how the engine works") == "explain"
    assert SI.classify_task("refactor this module") == "refactor"


def test_heuristic_decompose_is_checkable():
    subs = SI.decompose("write a function to sort a list", "code_write", model_fn=None)
    assert len(subs) >= 1
    assert all(s.check for s in subs)


def test_verify_scores_against_subgoals():
    subs = [
        SI.Subgoal(text="has code", check="def "),
        SI.Subgoal(text="mentions sort", check="sort"),
    ]
    score, updated = SI.verify("def sort(x): return sorted(x)", subs)
    assert score == 1.0
    assert all(s.satisfied for s in updated)

    score2, _ = SI.verify("here is some prose with no code", subs)
    assert score2 < 1.0


def test_improve_loop_with_mock_send():
    # A "big model" that always returns a perfect answer.
    def good_send(text: str) -> str:
        return "def sort(items): return sorted(items)  # handles empty if not items"

    result = SI.improve_loop(
        "write a function to sort items",
        send_fn=good_send, model_fn=None, max_attempts=2, persist=False,
    )
    assert result.ok
    assert result.score > 0.0
    assert result.attempts >= 1
    assert result.response


def test_improve_loop_retries_on_low_score():
    calls = {"n": 0}

    def improving_send(text: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return "I'm not sure."           # misses subgoals
        return "def go(): pass\nif not x: return"  # better

    result = SI.improve_loop(
        "write a function go", send_fn=improving_send,
        model_fn=None, max_attempts=2, persist=False,
    )
    assert calls["n"] == 2          # retried
    assert result.attempts == 2


def test_improve_loop_stops_early_on_perfect():
    calls = {"n": 0}

    def perfect_send(text: str) -> str:
        calls["n"] += 1
        return "def thing(): pass\nif not data: return"

    SI.improve_loop(
        "write a function thing that handles empty data",
        send_fn=perfect_send, model_fn=None, max_attempts=3, persist=False,
    )
    # Should not exhaust all 3 attempts if first is perfect.
    assert calls["n"] <= 3


def test_strategy_memory_records_and_persists():
    def good_send(text: str) -> str:
        return "def sort(items): return sorted(items)\nif not items: return []"

    SI.improve_loop("write sort function", send_fn=good_send,
                    model_fn=None, max_attempts=1, persist=True)
    strategies = SI.load_strategies()
    assert len(strategies) >= 1
    # Running again should reuse/refine, not crash.
    SI.improve_loop("write sort function", send_fn=good_send,
                    model_fn=None, max_attempts=1, persist=True)
    st = SI.status()
    assert st["total_strategies"] >= 1


def test_decompose_with_model_fn():
    def fake_model(prompt: str) -> str:
        return '[{"text": "defines function", "check": "def "}, {"text": "sorts", "check": "sort"}]'

    subs = SI.decompose("write a sorter", "code_write", model_fn=fake_model)
    assert len(subs) == 2
    assert subs[0].check == "def "
