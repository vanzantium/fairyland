import json
from pathlib import Path
from typing import Any
import pip_config

def get_apps_json_path() -> Path:
    return pip_config.get_memory_path() / "apps.json"

def load_apps() -> list[dict[str, Any]]:
    p = get_apps_json_path()
    if not p.exists():
        return []
    with open(p, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return []

def save_apps(apps: list[dict[str, Any]]) -> None:
    p = get_apps_json_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(apps, f, indent=2)

def award_xp(app_name: str, amount: int = 10) -> dict[str, Any]:
    """
    Awards XP to an app shell. If XP crosses 100 threshold, levels up.
    Returns the app dict with level/xp updates.
    """
    if not app_name:
        return {"error": "No app name provided"}

    apps = load_apps()
    found_app = None
    
    for app in apps:
        if app.get("name", "").lower() == app_name.lower():
            found_app = app
            break
            
    if not found_app:
        found_app = {
            "name": app_name,
            "enabled": True,
            "level": 1,
            "xp": 0
        }
        apps.append(found_app)
        
    old_level = found_app.get("level", 1)
    current_xp = found_app.get("xp", 0)
    
    new_xp = current_xp + amount
    level_ups = new_xp // 100
    remainder_xp = new_xp % 100
    
    new_level = old_level + level_ups
    
    found_app["level"] = new_level
    found_app["xp"] = remainder_xp
    
    # Automatically enable the app if we are using it
    found_app["enabled"] = True
    
    save_apps(apps)

    try:
        import pip_app_skills
        pip_app_skills.award_app_xp(app_name, amount, evidence="XP awarded through Pip app interaction.")
    except Exception:
        pass
    
    return {
        "app": app_name,
        "old_level": old_level,
        "new_level": new_level,
        "xp_awarded": amount,
        "current_xp": remainder_xp,
        "leveled_up": level_ups > 0
    }
