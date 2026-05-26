import time
import json
import urllib.request
import pip_config
import pip_skills
import pip_safety
import pip_hardware_scanner

class PipGoalEngine:
    def __init__(self, target_model="qwen2.5:0.5b", max_steps=15): # Small default for weak hardware
        self.target_model = target_model
        self.max_steps = max_steps
        self.brain_path = pip_config.get_memory_path()

    def get_hardware_model(self):
        try:
            hw_path = self.brain_path / "hardware.json"
            if not hw_path.exists():
                pip_hardware_scanner.scan_and_save()
            with open(hw_path, "r", encoding="utf-8") as f:
                hw = json.load(f)
                rec = hw.get("recommendation", {})
                return rec.get("model", self.target_model).split(" or ")[0]
        except Exception:
            return self.target_model

    def run_goal(self, goal: str, yield_logs=True, log_fn=None, should_stop=None):
        def emit(message: str) -> None:
            if log_fn:
                log_fn(message)
            if yield_logs:
                print(message)

        model = self.get_hardware_model()
        system_prompt = f"""You are Pip, an autonomous AI agent living on the user's PC.
You are running in autonomous /goal mode. Your goal is: {goal}

You have the following tools available. To use a tool, you MUST output ONLY valid JSON in this exact format:
{{
  "thought": "your reasoning here",
  "tool": "tool_name",
  "args": {{"arg1": "value"}}
}}

Tools:
- read_brain_file: Reads a file from the brain directory. Args: {{"filename": "file.txt"}}
- write_brain_file: Writes a file to the brain directory. Args: {{"filename": "file.txt", "content": "text"}}
- search_brain: Searches memory. Args: {{"query": "search term"}}
- finish_goal: Call this when you are done. Args: {{"message": "I finished!"}}

Do not request code execution, keyboard/mouse automation, app control, or system changes in goal mode.
Those actions must be queued for human approval instead of being run directly.
If you output anything other than JSON, it will fail.
"""
        messages = [{"role": "system", "content": system_prompt}]
        allowed_tools = {"read_brain_file", "write_brain_file", "search_brain"}
        
        for step in range(self.max_steps):
            if should_stop and should_stop():
                return "Stopped by user request."
            try:
                data = {
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "format": "json" # Force JSON output if supported
                }
                url = "http://localhost:11434/api/chat"
                req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers={"Content-Type": "application/json"})
                
                with urllib.request.urlopen(req, timeout=300) as response:
                    res_data = json.loads(response.read().decode("utf-8"))
                    content = res_data.get("message", {}).get("content", "")
                
                messages.append({"role": "assistant", "content": content})
                
                # Parse JSON
                try:
                    import re
                    # Robust JSON extraction to prevent JSONDecodeError from trailing LLM hallucinations
                    match = re.search(r'\{.*\}', content, re.DOTALL)
                    extracted_content = match.group(0) if match else content
                    
                    action = json.loads(extracted_content)
                    thought = action.get("thought", "No thought")
                    tool = action.get("tool", "")
                    args = action.get("args", {})
                    
                    emit(f"[Pip Thought]: {thought}")
                    emit(f"[Pip Action]: {tool} {args}")
                        
                    if tool == "finish_goal":
                        return args.get("message") or action.get("message", "Finished!")
                        
                    # Execute only low-risk goal tools. High-risk work becomes a permission request.
                    if tool in allowed_tools and tool in pip_skills.SKILLS:
                        # Convert dict to argparse.Namespace-like object
                        class ArgsWrapper:
                            def __init__(self, **kw):
                                for k,v in kw.items():
                                    setattr(self, k, v)
                        
                        tool_func = pip_skills.SKILLS[tool][1]
                        result = tool_func(ArgsWrapper(**args))
                        
                        emit(f"[Pip Result]: {result}")
                            
                        messages.append({"role": "user", "content": json.dumps(result)})
                    elif tool in pip_safety.DANGEROUS_SKILL_ACTIONS:
                        request = pip_safety.request_safety_permission(
                            pip_safety.DANGEROUS_SKILL_ACTIONS[tool],
                            title=f"Autonomous goal requested {tool}",
                            rationale=f"Goal: {goal}",
                            details={"goal": goal, "tool": tool, "args": args},
                        )
                        blocked = {
                            "blocked": True,
                            "message": "This tool needs human approval and was queued instead of executed.",
                            "permission_request": request,
                        }
                        emit(f"[Pip Safety]: {blocked}")
                        messages.append({"role": "user", "content": json.dumps(blocked)})
                    else:
                        messages.append({"role": "user", "content": json.dumps({"error": f"Tool {tool} not found"})})
                        
                except json.JSONDecodeError:
                    messages.append({"role": "user", "content": json.dumps({"error": "Failed to parse JSON. You MUST return valid JSON."})})
                    
            except Exception as e:
                return f"Agent loop failed: {e}"
                
        return "Reached maximum steps without finishing."
