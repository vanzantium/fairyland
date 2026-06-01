"""
pip_self_improve.py — Strategy learning loop, BES-inspired.

Adapted from "Self-Improving Language Models with Bidirectional
Evolutionary Search" (arXiv:2605.28814) for the no-API, small-model-
orchestrating-big-model setup that Pip runs:

  - Backward search: a tiny local model decomposes a task into CHECKABLE
    subgoals. These give dense intermediate feedback instead of one
    sparse pass/fail at the end.
  - Forward search: generate several candidate phrasings of the task,
    and RECOMBINE fragments from strategies that worked before — letting
    a weak model escape the "narrow entropy shell" of single-shot prompts.

Crucially, nothing here fine-tunes a model. The "improvement" is a growing
StrategyMemory of decompositions and phrasings scored by how well the
big model's response satisfied the checkable subgoals. Over time Pip gets
better at ASKING, which is most of the battle when orchestrating tools
through the text bridge.

The loop is dependency-light and testable: the big model is reached through
an injected `send_fn`, and decomposition falls back to heuristics when no
local model (Ollama) is available.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from . import pip_config


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Subgoal:
    text: str
    check: str           # a keyword/phrase whose presence signals success
    satisfied: bool = False


@dataclass
class Strategy:
    """A reusable way of phrasing/framing a task that worked before."""
    task_type: str
    framing: str         # prefix/scaffold added to the raw task
    subgoal_checks: list[str] = field(default_factory=list)
    score: float = 0.0   # rolling success score 0..1
    uses: int = 0
    created_at: str = field(default_factory=utc_now)


@dataclass
class ImproveResult:
    ok: bool
    task: str
    task_type: str
    framing_used: str
    sent_text: str
    response: str
    subgoals: list[dict[str, Any]]
    score: float
    attempts: int
    error: str = ""


# ---------------------------------------------------------------------------
# Strategy memory (persistent JSON, the "learning" substrate)
# ---------------------------------------------------------------------------

def memory_path() -> Path:
    return pip_config.get_memory_path() / "strategy_memory.json"


def load_strategies() -> dict[str, list[Strategy]]:
    path = memory_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        out: dict[str, list[Strategy]] = {}
        for task_type, items in raw.items():
            out[task_type] = [Strategy(**it) for it in items]
        return out
    except Exception:
        return {}


def save_strategies(strategies: dict[str, list[Strategy]]) -> None:
    path = memory_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        task_type: [asdict(s) for s in sorted(items, key=lambda s: s.score, reverse=True)[:12]]
        for task_type, items in strategies.items()
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Task typing
# ---------------------------------------------------------------------------

_TYPE_KEYWORDS = {
    "code_write": ["write", "implement", "create", "add", "build", "function", "class"],
    "code_fix": ["fix", "bug", "error", "broken", "fails", "debug"],
    "code_review": ["review", "check", "audit", "look at", "assess"],
    "refactor": ["refactor", "clean up", "simplify", "reorganize", "rename"],
    "explain": ["explain", "what does", "how does", "why", "summarize", "describe"],
    "test": ["test", "verify", "validate", "cover"],
}


def classify_task(task: str) -> str:
    lowered = (task or "").lower()
    best, best_hits = "general", 0
    for ttype, kws in _TYPE_KEYWORDS.items():
        hits = sum(1 for kw in kws if kw in lowered)
        if hits > best_hits:
            best, best_hits = ttype, hits
    return best


# ---------------------------------------------------------------------------
# Backward search: decompose task into checkable subgoals
# ---------------------------------------------------------------------------

def _heuristic_subgoals(task: str, task_type: str) -> list[Subgoal]:
    """Decompose without a model — checkable, task-type aware."""
    base: dict[str, list[tuple[str, str]]] = {
        "code_write": [
            ("Produces code, not just prose", "def "),
            ("Addresses the named thing", _key_noun(task)),
            ("Handles an edge/empty case", "if "),
        ],
        "code_fix": [
            ("Identifies the cause", "because"),
            ("Shows a corrected version", "def "),
        ],
        "code_review": [
            ("Names specific issues", "issue"),
            ("Gives a concrete suggestion", "suggest"),
        ],
        "refactor": [
            ("Keeps behavior, changes shape", "same"),
            ("Shows the new structure", "def "),
        ],
        "explain": [
            ("Answers the question directly", _key_noun(task)),
            ("Stays concise", " "),
        ],
        "test": [
            ("Provides a test", "assert"),
            ("Covers the target", _key_noun(task)),
        ],
    }
    pairs = base.get(task_type, [("Addresses the request", _key_noun(task))])
    return [Subgoal(text=t, check=c) for t, c in pairs if c]


def _key_noun(task: str) -> str:
    """Pull a salient word from the task to check the response stays on-topic."""
    words = [w.strip(".,!?:;\"'`()") for w in (task or "").split()]
    stop = {"the", "a", "an", "to", "for", "of", "in", "on", "and", "or",
            "this", "that", "please", "can", "you", "with", "my", "me", "it"}
    cands = [w for w in words if len(w) > 3 and w.lower() not in stop]
    return cands[0].lower() if cands else ""


def decompose(task: str, task_type: str, model_fn: Optional[Callable[[str], str]] = None) -> list[Subgoal]:
    """
    Break a task into checkable subgoals. Uses a local model if one is
    provided; otherwise falls back to heuristics.
    """
    if model_fn is not None:
        prompt = (
            "Break this task into 2-4 checkable subgoals. For each, give a short "
            "phrase that would appear in a correct answer.\n"
            f"Task: {task}\n"
            'Reply as JSON: [{"text": "...", "check": "..."}]'
        )
        try:
            raw = model_fn(prompt)
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                items = json.loads(match.group(0))
                subs = [
                    Subgoal(text=str(it.get("text", "")), check=str(it.get("check", "")).lower())
                    for it in items if it.get("check")
                ]
                if subs:
                    return subs[:4]
        except Exception:
            pass
    return _heuristic_subgoals(task, task_type)


# ---------------------------------------------------------------------------
# Forward search: generate candidate framings, recombining what worked
# ---------------------------------------------------------------------------

def generate_framings(
    task_type: str,
    subgoals: list[Subgoal],
    strategies: dict[str, list[Strategy]],
    n: int = 3,
) -> list[str]:
    """
    Produce candidate framings. Seeds from past winners and RECOMBINES
    their fragments (the evolutionary operator) to escape single-shot phrasing.
    """
    checks = "; ".join(s.text for s in subgoals)
    framings: list[str] = []

    # 1. Baseline framing: state the checkable subgoals up front.
    framings.append(
        f"Please address all of these, concretely: {checks}."
    )

    # 2. Past winners for this task type.
    past = sorted(strategies.get(task_type, []), key=lambda s: s.score, reverse=True)
    for s in past[:2]:
        if s.framing and s.framing not in framings:
            framings.append(s.framing)

    # 3. Recombination: splice the best framing's opener with the subgoal list.
    if past:
        opener = past[0].framing.split(".")[0]
        recombined = f"{opener}. Make sure to cover: {checks}."
        if recombined not in framings:
            framings.append(recombined)

    # 4. A terse variant — small models often do better with less scaffolding.
    framings.append(f"Be specific and complete. Cover: {checks}.")

    return framings[:n]


# ---------------------------------------------------------------------------
# Verification: score a response against the subgoals
# ---------------------------------------------------------------------------

def verify(response: str, subgoals: list[Subgoal]) -> tuple[float, list[Subgoal]]:
    """Check the response against each subgoal. Returns (score, updated subgoals)."""
    if not subgoals:
        return (1.0 if response.strip() else 0.0), subgoals
    lowered = (response or "").lower()
    satisfied = 0
    for s in subgoals:
        check = (s.check or "").lower().strip()
        s.satisfied = bool(check) and check in lowered
        if s.satisfied:
            satisfied += 1
    return satisfied / len(subgoals), subgoals


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------

def improve_loop(
    task: str,
    send_fn: Callable[[str], str],
    model_fn: Optional[Callable[[str], str]] = None,
    max_attempts: int = 2,
    persist: bool = True,
) -> ImproveResult:
    """
    Orchestrate one self-improving exchange.

    send_fn(text) -> response   (e.g. the text bridge to Claude Code)
    model_fn(prompt) -> text    (optional local model for decomposition)

    Decompose → frame (forward search) → send → verify → record. If subgoals
    are unmet, recombine a stronger framing and retry up to max_attempts.
    """
    task_type = classify_task(task)
    strategies = load_strategies()
    subgoals = decompose(task, task_type, model_fn)
    framings = generate_framings(task_type, subgoals, strategies, n=max(2, max_attempts + 1))

    best: Optional[ImproveResult] = None

    for attempt in range(max_attempts):
        framing = framings[min(attempt, len(framings) - 1)]
        sent = f"{framing}\n\nTask: {task}"
        try:
            response = send_fn(sent)
        except Exception as exc:
            return ImproveResult(
                ok=False, task=task, task_type=task_type, framing_used=framing,
                sent_text=sent, response="", subgoals=[asdict(s) for s in subgoals],
                score=0.0, attempts=attempt + 1, error=str(exc),
            )

        # Fresh subgoal copies per attempt so satisfied flags don't leak.
        attempt_subs = [Subgoal(text=s.text, check=s.check) for s in subgoals]
        score, attempt_subs = verify(response, attempt_subs)

        result = ImproveResult(
            ok=True, task=task, task_type=task_type, framing_used=framing,
            sent_text=sent, response=response,
            subgoals=[asdict(s) for s in attempt_subs],
            score=score, attempts=attempt + 1,
        )

        if best is None or score > best.score:
            best = result

        _record_strategy(strategies, task_type, framing, subgoals, score)

        if score >= 0.99:
            break  # all subgoals met — no need to retry

    if persist:
        save_strategies(strategies)

    return best  # type: ignore[return-value]


def _record_strategy(
    strategies: dict[str, list[Strategy]],
    task_type: str,
    framing: str,
    subgoals: list[Subgoal],
    score: float,
) -> None:
    bucket = strategies.setdefault(task_type, [])
    for s in bucket:
        if s.framing == framing:
            # Rolling average toward the latest outcome.
            s.score = round(0.7 * s.score + 0.3 * score, 4)
            s.uses += 1
            return
    bucket.append(Strategy(
        task_type=task_type,
        framing=framing,
        subgoal_checks=[s.check for s in subgoals],
        score=round(score, 4),
        uses=1,
    ))


# ---------------------------------------------------------------------------
# Optional local-model helper (Ollama) — used for decomposition if present
# ---------------------------------------------------------------------------

def ollama_model_fn(model: str = "qwen2.5:0.5b", timeout: int = 60) -> Callable[[str], str]:
    """Build a model_fn backed by a local Ollama instance via its native API."""
    import urllib.request

    def call(prompt: str) -> str:
        data = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        req = urllib.request.Request(
            "http://localhost:11434/api/chat",
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            return res.get("message", {}).get("content", "")

    return call


def openai_compat_model_fn(
    base_url: str = "http://127.0.0.1:11434/v1",
    model: str = "qwen2.5:0.5b",
    api_key: str = "",
    timeout: int = 60,
) -> Callable[[str], str]:
    """
    Build a model_fn backed by ANY OpenAI-compatible /v1 endpoint.

    This is the backend-agnostic path: the same function talks to llama.cpp's
    llama-server, LM Studio, Jan, or Ollama (all of which serve
    /v1/chat/completions). Lets Pip use whatever local model the user already
    has running, with no paid API.
    """
    import urllib.request

    url = base_url.rstrip("/") + "/chat/completions"

    def call(prompt: str) -> str:
        data = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        req = urllib.request.Request(
            url, data=json.dumps(data).encode("utf-8"), headers=headers,
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            choices = res.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            return ""

    return call


def local_model_fn() -> Optional[Callable[[str], str]]:
    """
    Resolve the user's configured local model into a model_fn.

    Honors pip_config.get_llm_config(): the OpenAI-compatible adapter is the
    default so it works across backends; "ollama" forces the native API;
    "none" disables local inference (Pip falls back to heuristics / the bridge).
    Returns None when no local backend is configured.
    """
    cfg = pip_config.get_llm_config()
    backend = cfg.get("backend", "openai_compat")
    timeout = int(cfg.get("timeout_s", 60))
    if backend == "none":
        return None
    if backend == "ollama":
        return ollama_model_fn(model=cfg.get("model", "qwen2.5:0.5b"), timeout=timeout)
    return openai_compat_model_fn(
        base_url=cfg.get("base_url", "http://127.0.0.1:11434/v1"),
        model=cfg.get("model", "qwen2.5:0.5b"),
        api_key=cfg.get("api_key", ""),
        timeout=timeout,
    )


def status() -> dict[str, Any]:
    strategies = load_strategies()
    return {
        "task_types_learned": list(strategies.keys()),
        "total_strategies": sum(len(v) for v in strategies.values()),
        "top_strategies": {
            ttype: [
                {"framing": s.framing[:80], "score": s.score, "uses": s.uses}
                for s in sorted(items, key=lambda s: s.score, reverse=True)[:3]
            ]
            for ttype, items in strategies.items()
        },
    }
