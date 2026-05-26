"""
pip_personas.py — The Persona Orchestrator for the Digital Tavern.
Manages loading persona shells and dispatching tasks via UI automation.
"""
import os
import json
import time
from pathlib import Path
import pip_hands
import pip_evolution
import pip_safety

PERSONAS_DIR = Path(__file__).resolve().parent / "personas"

def load_personas() -> dict:
    """Loads all available persona configurations."""
    personas = {}
    if not PERSONAS_DIR.exists():
        PERSONAS_DIR.mkdir()
        return personas
        
    for pfile in PERSONAS_DIR.glob("*.json"):
        try:
            config = json.loads(pfile.read_text(encoding="utf-8"))
            if "name" in config:
                personas[config["name"].lower()] = config
                for alias in config.get("aliases", []):
                    personas[str(alias).lower()] = config
        except Exception as e:
            print(f"[personas] Failed to load {pfile.name}: {e}")
            
    return personas

def focus_window_by_title(title_snippet: str) -> bool:
    """Tries to bring a window containing the title_snippet to the foreground."""
    try:
        import pygetwindow as gw
        windows = gw.getWindowsWithTitle(title_snippet)
        if windows:
            win = windows[0]
            if win.isMinimized:
                win.restore()
            try:
                win.activate()
            except Exception as e:
                # Background processes often can't steal focus natively. 
                # Fallback: physical click the title bar or center of the window.
                try:
                    import pyautogui
                    pyautogui.click(win.left + win.width // 2, win.top + win.height // 2)
                except Exception:
                    pass
            time.sleep(0.5)
            return True
    except ImportError:
        pass
    except Exception as e:
        pass
    
    return False

def dispatch_task(persona_name: str, task_text: str) -> dict:
    """Dispatches a text task to a specific persona via UI macros."""
    personas = load_personas()
    name = persona_name.lower().replace("@", "")
    
    if name not in personas:
        return {"ok": False, "message": f"I couldn't find a persona named {persona_name} in the Tavern."}
        
    config = personas[name]
    macros = config.get("macros", {}).get("submit_task", [])
    
    if not macros:
        return {"ok": False, "message": f"Persona {persona_name} doesn't know how to submit tasks!"}

    request = pip_safety.request_safety_permission(
        "ui_automation",
        title=f"Approve persona handoff: {persona_name}",
        rationale=f"Submit task to {config.get('app_name', name)} using UI automation.",
        details={"persona": persona_name, "app": config.get("app_name", name), "task": task_text},
    )
    return {
        "ok": False,
        "blocked": True,
        "message": f"I queued the {persona_name} handoff for approval before touching {config.get('app_name', name)}.",
        "permission_request": request,
    }
        
    # Execute the macro sequence
    print(f"[personas] Dispatching task to {persona_name}...")
    for step in macros:
        action = step.get("action")
        if action == "focus_window":
            # Attempt to focus the app
            success = focus_window_by_title(config.get("window_title", ""))
            if not success:
                # If we can't find it, we prompt the user to open it manually.
                return {"ok": False, "message": f"I couldn't find the {config.get('app_name')} window. Please open it so {persona_name} can take over!"}
                
        elif action == "type_text":
            source = step.get("source")
            text_to_type = task_text if source == "task_input" else step.get("text", "")
            if pip_hands.type_text(text_to_type, interval=0.02):
                pip_evolution.award_xp(config.get("app_name", name), 5)
            
        elif action == "press_key":
            key = step.get("key")
            if pip_hands.press_key(key):
                pip_evolution.award_xp(config.get("app_name", name), 2)
            
        time.sleep(0.5) # Slight pause between macro steps
        
    return {"ok": True, "message": f"I've handed the task off to {config.get('app_name', name)}! Check the control panel to see if this app leveled up."}
