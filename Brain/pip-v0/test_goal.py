import sys
from pathlib import Path
import os

# Add to sys.path so we can import pip modules
sys.path.append(str(Path(__file__).resolve().parent))

from pip_goal_engine import PipGoalEngine

def test_goal():
    if os.environ.get("PIP_RUN_LIVE_GOAL_TEST") != "1":
        print("Skipped live goal demo. Set PIP_RUN_LIVE_GOAL_TEST=1 to run it manually.")
        return

    print("Testing Goal Engine...")
    engine = PipGoalEngine(max_steps=5) # 5 steps max for safety in test
    result = engine.run_goal("Hello Pip! Please write a file called pip_hello.txt in the brain memory folder containing a polite greeting.")
    print("FINAL RESULT:", result)

if __name__ == "__main__":
    test_goal()
