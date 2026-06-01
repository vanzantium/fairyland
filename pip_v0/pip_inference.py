"""
pip_inference.py — Local-first inference router.

Turns Pip's "no expensive APIs if at all possible" policy into enforced code.
Inspired by the unified-client pattern in orailnoor/cross-platform-llm-client
(PrivateLM): one interface, swappable backends, a capability check, and a
graceful fallback chain.

The chain, in order of preference:

    1. LOCAL   — a model on this machine via an OpenAI-compatible /v1 endpoint
                 (llama.cpp, LM Studio, Jan, Ollama). Free, private, offline.
    2. BRIDGE  — type the prompt into an external tool (Claude Code, Codex…)
                 and harvest the reply via the clipboard. No API key. Gated by
                 the security sentinel, because it steals the keyboard.
    3. CLOUD   — a paid API. Only ever reached when the user has explicitly
                 opted in (config: llm.allow_cloud = true). Off by default.

If nothing is available, Pip degrades to heuristics rather than spending money.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from . import pip_config
from . import pip_self_improve
from . import pip_sentinel


SOURCE_LOCAL = "local"
SOURCE_BRIDGE = "bridge"
SOURCE_CLOUD = "cloud"
SOURCE_NONE = "none"


@dataclass
class InferenceResult:
    ok: bool
    text: str
    source: str            # which backend answered (local/bridge/cloud/none)
    model: str = ""
    error: str = ""
    blocked: bool = False   # true if a backend was refused (e.g. sentinel)


def _local_reachable(model_fn) -> bool:
    if model_fn is None:
        return False
    try:
        model_fn("ping")
        return True
    except Exception:
        return False


def capabilities() -> dict:
    """
    Report which backends are usable right now — the `supportsLocalInference`
    capability check, generalized. Cheap probes only.
    """
    cfg = pip_config.get_llm_config()
    model_fn = None
    local_ok = False
    if cfg.get("backend", "openai_compat") != "none":
        try:
            model_fn = pip_self_improve.local_model_fn()
            local_ok = _local_reachable(model_fn)
        except Exception:
            local_ok = False
    return {
        "local": local_ok,
        "backend": cfg.get("backend"),
        "base_url": cfg.get("base_url"),
        "model": cfg.get("model"),
        "bridge": pip_sentinel.autonomy_allowed(),
        "cloud_allowed": bool(cfg.get("allow_cloud")),
    }


def complete(
    prompt: str,
    *,
    allow_bridge: bool = False,
    bridge_persona: Optional[str] = None,
    bridge_wait_s: float | None = None,
) -> InferenceResult:
    """
    Run a single completion through the fallback chain.

    By default only LOCAL is attempted (cheapest, private). Set allow_bridge
    to let Pip fall back to the text bridge when no local model is present —
    but only if the security sentinel permits autonomous keyboard use.
    """
    cfg = pip_config.get_llm_config()
    model = cfg.get("model", "")

    # 1. LOCAL — preferred.
    if cfg.get("backend", "openai_compat") != "none":
        try:
            model_fn = pip_self_improve.local_model_fn()
            if model_fn is not None:
                text = model_fn(prompt)
                if text and text.strip():
                    return InferenceResult(True, text, SOURCE_LOCAL, model=model)
        except Exception as exc:
            # fall through to the next backend
            local_error = str(exc)
        else:
            local_error = "local model returned nothing"
    else:
        local_error = "local backend disabled"

    # 2. BRIDGE — sentinel-gated keyboard handoff.
    if allow_bridge and bridge_persona:
        if not pip_sentinel.autonomy_allowed():
            return InferenceResult(
                False, "", SOURCE_BRIDGE, blocked=True,
                error=f"Bridge blocked by security posture "
                      f"{pip_sentinel.status().get('posture')}.",
            )
        try:
            from . import pip_text_bridge
            res = pip_text_bridge.send(bridge_persona, prompt, response_wait_s=bridge_wait_s)
            if res.ok and res.response.strip():
                return InferenceResult(True, res.response, SOURCE_BRIDGE, model=bridge_persona)
            return InferenceResult(
                False, res.response, SOURCE_BRIDGE,
                error=res.error or "bridge returned nothing",
            )
        except Exception as exc:
            return InferenceResult(False, "", SOURCE_BRIDGE, error=str(exc))

    # 3. CLOUD — opt-in only. We do NOT silently call paid APIs.
    if cfg.get("allow_cloud"):
        # A cloud endpoint is just an OpenAI-compatible backend with a real
        # base_url + key; the user configures it deliberately. If they enabled
        # cloud but local was the configured backend, there is nothing to call
        # here without separate cloud settings, so we report honestly.
        return InferenceResult(
            False, "", SOURCE_CLOUD,
            error="Cloud allowed but no separate cloud endpoint is configured.",
        )

    return InferenceResult(False, "", SOURCE_NONE, error=local_error)


def status() -> dict:
    """Dashboard-friendly snapshot of the inference layer."""
    caps = capabilities()
    if caps["local"]:
        preferred = SOURCE_LOCAL
    elif caps["bridge"]:
        preferred = SOURCE_BRIDGE
    elif caps["cloud_allowed"]:
        preferred = SOURCE_CLOUD
    else:
        preferred = SOURCE_NONE
    return {
        "preferred_source": preferred,
        "capabilities": caps,
        "policy": "local-first; bridge needs CALM/WATCH posture; cloud opt-in only",
    }
