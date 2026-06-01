import json
import os
from pathlib import Path

from . import pip_platform

CONFIG_PATH = Path(__file__).resolve().parent / "config.json"
DEFAULT_MEMORY_PATH = Path(__file__).resolve().parent / "PipMemory"

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_config(config: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

def get_memory_path() -> Path:
    env_path = os.environ.get("PIP_MEMORY_PATH")
    if env_path:
        p = Path(env_path).expanduser()
        if not p.is_absolute():
            p = pip_platform.BRAIN_ROOT / p
        p.mkdir(parents=True, exist_ok=True)
        return p

    config = load_config()
    path_str = config.get("memory_folder_path", "")
    if not path_str:
        DEFAULT_MEMORY_PATH.mkdir(parents=True, exist_ok=True)
        return DEFAULT_MEMORY_PATH
    
    p = Path(path_str)
    if not p.is_absolute():
        p = Path(__file__).resolve().parent / p
        
    p.mkdir(parents=True, exist_ok=True)
    return p

def set_memory_path(path_str: str) -> None:
    config = load_config()
    config["memory_folder_path"] = str(path_str)
    save_config(config)


# ---------------------------------------------------------------------------
# Local LLM backend config
#
# Pip prefers a LOCAL model and never requires a paid API. The backend is
# reached through an OpenAI-compatible /v1 endpoint, so the same config works
# for llama.cpp's llama-server, LM Studio, Jan, and Ollama (which also serves
# /v1). Env vars win over config.json so a phone/Termux install can override
# without editing files.
# ---------------------------------------------------------------------------

DEFAULT_LLM = {
    "backend": "openai_compat",          # openai_compat | ollama | none
    "base_url": "http://127.0.0.1:11434/v1",  # Ollama's OpenAI-compatible port
    "model": "qwen2.5:0.5b",
    "api_key": "",                       # local servers ignore this
    "allow_cloud": False,                # never call paid APIs unless opted in
    "timeout_s": 60,
}


def get_llm_config() -> dict:
    """Resolve the local-LLM config (env vars override config.json)."""
    cfg = dict(DEFAULT_LLM)
    stored = load_config().get("llm", {})
    if isinstance(stored, dict):
        cfg.update({k: v for k, v in stored.items() if v is not None})
    env_map = {
        "PIP_LLM_BACKEND": "backend",
        "PIP_LLM_BASE_URL": "base_url",
        "PIP_LLM_MODEL": "model",
        "PIP_LLM_API_KEY": "api_key",
    }
    for env_key, cfg_key in env_map.items():
        val = os.environ.get(env_key)
        if val:
            cfg[cfg_key] = val
    if os.environ.get("PIP_LLM_ALLOW_CLOUD"):
        cfg["allow_cloud"] = os.environ["PIP_LLM_ALLOW_CLOUD"].lower() in ("1", "true", "yes")
    return cfg


def set_llm_config(**kwargs) -> dict:
    """Persist partial LLM config to config.json. Returns the merged config."""
    config = load_config()
    llm = dict(config.get("llm", {}))
    for k, v in kwargs.items():
        if k in DEFAULT_LLM:
            llm[k] = v
    config["llm"] = llm
    save_config(config)
    return get_llm_config()
