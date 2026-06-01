"""Tests for pip_inference — the local-first fallback router."""

import os
import tempfile

os.environ["PIP_MEMORY_PATH"] = tempfile.mkdtemp(prefix="pip_inference_test_")

from pip_v0 import pip_inference as I
from pip_v0 import pip_sentinel as S
from pip_v0 import pip_self_improve as SI


def test_local_success(monkeypatch):
    monkeypatch.setattr(SI, "local_model_fn", lambda: (lambda p: "hello from local"))
    monkeypatch.setattr(I.pip_config, "get_llm_config",
                        lambda: {"backend": "openai_compat", "model": "m", "allow_cloud": False})
    res = I.complete("hi")
    assert res.ok is True
    assert res.source == I.SOURCE_LOCAL
    assert res.text == "hello from local"


def test_falls_back_to_bridge_when_no_local(monkeypatch):
    monkeypatch.setattr(SI, "local_model_fn", lambda: None)
    monkeypatch.setattr(I.pip_config, "get_llm_config",
                        lambda: {"backend": "openai_compat", "model": "m", "allow_cloud": False})
    monkeypatch.setattr(I.pip_sentinel, "autonomy_allowed", lambda: True)

    from types import SimpleNamespace
    from pip_v0 import pip_text_bridge
    monkeypatch.setattr(
        pip_text_bridge, "send",
        lambda persona, prompt, response_wait_s=None:
            SimpleNamespace(ok=True, response="from bridge", error=""),
    )
    res = I.complete("hi", allow_bridge=True, bridge_persona="claude")
    assert res.ok is True
    assert res.source == I.SOURCE_BRIDGE
    assert res.text == "from bridge"


def test_bridge_blocked_by_sentinel(monkeypatch):
    monkeypatch.setattr(SI, "local_model_fn", lambda: None)
    monkeypatch.setattr(I.pip_config, "get_llm_config",
                        lambda: {"backend": "openai_compat", "model": "m", "allow_cloud": False})
    monkeypatch.setattr(I.pip_sentinel, "autonomy_allowed", lambda: False)
    monkeypatch.setattr(I.pip_sentinel, "status", lambda: {"posture": "LOCK"})
    res = I.complete("hi", allow_bridge=True, bridge_persona="claude")
    assert res.ok is False
    assert res.blocked is True
    assert res.source == I.SOURCE_BRIDGE


def test_no_backend_returns_none_source(monkeypatch):
    monkeypatch.setattr(I.pip_config, "get_llm_config",
                        lambda: {"backend": "none", "model": "", "allow_cloud": False})
    res = I.complete("hi")
    assert res.ok is False
    assert res.source == I.SOURCE_NONE


def test_cloud_not_called_silently(monkeypatch):
    # Local disabled, no bridge, cloud allowed but unconfigured -> honest failure.
    monkeypatch.setattr(I.pip_config, "get_llm_config",
                        lambda: {"backend": "none", "model": "", "allow_cloud": True})
    res = I.complete("hi")
    assert res.ok is False
    assert res.source == I.SOURCE_CLOUD


def test_capabilities_shape(monkeypatch):
    monkeypatch.setattr(SI, "local_model_fn", lambda: (lambda p: "ok"))
    monkeypatch.setattr(I.pip_config, "get_llm_config",
                        lambda: {"backend": "openai_compat", "base_url": "x", "model": "m", "allow_cloud": False})
    monkeypatch.setattr(I.pip_sentinel, "autonomy_allowed", lambda: True)
    caps = I.capabilities()
    assert caps["local"] is True
    assert caps["bridge"] is True
    assert caps["cloud_allowed"] is False


def test_local_model_fn_respects_config(monkeypatch):
    monkeypatch.setattr(SI.pip_config, "get_llm_config",
                        lambda: {"backend": "none", "model": "m", "timeout_s": 5})
    assert SI.local_model_fn() is None

    monkeypatch.setattr(SI.pip_config, "get_llm_config",
                        lambda: {"backend": "openai_compat", "base_url": "http://x/v1",
                                 "model": "m", "api_key": "", "timeout_s": 5})
    fn = SI.local_model_fn()
    assert callable(fn)
