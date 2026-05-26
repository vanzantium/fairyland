import json
import os
from pathlib import Path

import pip_platform

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
