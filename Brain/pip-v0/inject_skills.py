import re

def run():
    with open('pip_skills.py', 'r', encoding='utf-8') as f:
        content = f.read()
        
    hands_code = """
def hands_type_text(args: argparse.Namespace) -> dict[str, Any]:
    try:
        import pip_hands
        import pip_evolution
    except ImportError:
        return {"skill": "hands_type_text", "ok": False, "message": "Module not found."}
    
    text = getattr(args, "content", "")
    target_app = getattr(args, "target_app", "")
    
    if pip_hands.type_text(text):
        if target_app:
            xp_data = pip_evolution.award_xp(target_app, 5)
            return {"skill": "hands_type_text", "ok": True, "xp_data": xp_data}
        return {"skill": "hands_type_text", "ok": True}
    return {"skill": "hands_type_text", "ok": False, "message": "Typing failed or failsafe triggered."}

def hands_press_key(args: argparse.Namespace) -> dict[str, Any]:
    try:
        import pip_hands
        import pip_evolution
    except ImportError:
        return {"skill": "hands_press_key", "ok": False, "message": "Module not found."}
    
    key = getattr(args, "key", "")
    target_app = getattr(args, "target_app", "")
    
    if pip_hands.press_key(key):
        if target_app:
            xp_data = pip_evolution.award_xp(target_app, 2)
            return {"skill": "hands_press_key", "ok": True, "xp_data": xp_data}
        return {"skill": "hands_press_key", "ok": True}
    return {"skill": "hands_press_key", "ok": False, "message": "Key press failed or failsafe triggered."}

def hands_click_mouse(args: argparse.Namespace) -> dict[str, Any]:
    try:
        import pip_hands
        import pip_evolution
    except ImportError:
        return {"skill": "hands_click_mouse", "ok": False, "message": "Module not found."}
    
    x = getattr(args, "x", None)
    y = getattr(args, "y", None)
    target_app = getattr(args, "target_app", "")
    
    x_val = int(x) if x is not None else None
    y_val = int(y) if y is not None else None
    
    if pip_hands.click_mouse(x=x_val, y=y_val):
        if target_app:
            xp_data = pip_evolution.award_xp(target_app, 3)
            return {"skill": "hands_click_mouse", "ok": True, "xp_data": xp_data}
        return {"skill": "hands_click_mouse", "ok": True}
    return {"skill": "hands_click_mouse", "ok": False, "message": "Click failed."}

def record_new_macro"""
    
    content = content.replace("def record_new_macro", hands_code)

    skills_dict_inject = """    "hands_type_text": (
        SkillSpec(
            name="hands_type_text",
            description="Type text out via pyautogui.",
            inputs=["--content text", "--target-app app_name"],
            outputs=["success or xp_data"],
            permissions=["automate ui"],
        ),
        hands_type_text,
    ),
    "hands_press_key": (
        SkillSpec(
            name="hands_press_key",
            description="Press a specific key via pyautogui (e.g. enter, tab, win).",
            inputs=["--key keyname", "--target-app app_name"],
            outputs=["success or xp_data"],
            permissions=["automate ui"],
        ),
        hands_press_key,
    ),
    "hands_click_mouse": (
        SkillSpec(
            name="hands_click_mouse",
            description="Click the mouse at current location or specified x, y.",
            inputs=["--x x_coord", "--y y_coord", "--target-app app_name"],
            outputs=["success or xp_data"],
            permissions=["automate ui"],
        ),
        hands_click_mouse,
    ),
    "record_new_macro":"""

    content = content.replace('    "record_new_macro":', skills_dict_inject)

    parser_inject = """    run_parser.add_argument("--name", help="Name for recorded macro")
    run_parser.add_argument("--key", help="Key name for hands_press_key")
    run_parser.add_argument("--x", help="X coordinate for hands_click_mouse")
    run_parser.add_argument("--y", help="Y coordinate for hands_click_mouse")
    run_parser.add_argument("--target-app", help="Target App Name for Persona Evolution XP")
"""
    content = content.replace('    run_parser.add_argument("--name", help="Name for recorded macro")\n', parser_inject)

    with open('pip_skills.py', 'w', encoding='utf-8') as f:
        f.write(content)
        
    print("Injected hands skills successfully.")

if __name__ == '__main__':
    run()
