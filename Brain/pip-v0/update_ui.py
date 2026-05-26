import re
import html

def run():
    with open('pip_control_panel.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Find the start of def page(status: dict[str, Any]) -> str:
    # and the end of it (which is right before def fairy_page() -> str:)
    
    match = re.search(r'def page\(status: dict\[str, Any\]\) -> str:(.*?)def fairy_page\(\) -> str:', content, re.DOTALL)
    if not match:
        print("Could not find page() function")
        return
        
    old_page = match.group(0)

    new_page = '''def page(status: dict[str, Any]) -> str:
    import json
    from pathlib import Path
    import html
    
    proposal = status.get("latest_proposal") or {}
    status_label = proposal.get("status", "idle")
    proposal_text = proposal.get("proposal", "Pip is resting. Tap Run Scan to wake her.")
    
    # Load apps
    apps = []
    try:
        with open(Path("PipMemory") / "apps.json", "r", encoding="utf-8") as f:
            apps = json.load(f)
    except Exception:
        pass
        
    apps_html = ""
    for app in apps:
        checked = "checked" if app.get("enabled") else ""
        level = app.get("level", 1)
        xp = app.get("xp", 0)
        apps_html += f"""
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
            <label><input type="checkbox" name="app_{html.escape(app['name'])}" {checked}> {html.escape(app['name'])}</label>
            <span class="small" style="background: var(--leaf); padding: 2px 6px; border-radius: 4px;">Lvl {level} ({xp}xp)</span>
        </div>
        """
    if not apps_html:
        apps_html = "<p class='small'>No apps scanned yet. Run the scanner first.</p>"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Pip's Digital Tavern</title>
  <style>
    :root {{
      --ink: #182018;
      --moss: #5c6f43;
      --leaf: #d9e2be;
      --silk: #f8f3df;
      --clay: #b96f4d;
      --shadow: rgba(28, 36, 23, 0.16);
    }}
    body {{
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(217, 226, 190, .9), transparent 32rem),
        linear-gradient(140deg, #f8f3df 0%, #dfe8c7 54%, #c7d3a7 100%);
      font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    }}
    main {{
      max-width: 860px;
      margin: 0 auto;
      padding: 22px;
    }}
    .hero, .card {{
      background: rgba(255, 253, 240, .82);
      border: 1px solid rgba(92, 111, 67, .22);
      border-radius: 24px;
      box-shadow: 0 18px 50px var(--shadow);
      padding: 24px;
      margin: 20px 0;
    }}
    h1 {{
      font-size: clamp(2rem, 6vw, 3rem);
      margin: 0 0 10px;
      color: var(--ink);
    }}
    h2 {{
      margin: 0 0 15px;
      color: var(--moss);
      font-size: 1.4rem;
    }}
    p {{ line-height: 1.5; }}
    .pill {{
      display: inline-block;
      border-radius: 999px;
      background: var(--leaf);
      padding: 6px 12px;
      margin: 4px 6px 4px 0;
      font-size: .9rem;
      font-weight: 600;
    }}
    .actions {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 12px;
      margin-top: 15px;
    }}
    button {{
      width: 100%;
      border: 0;
      border-radius: 12px;
      padding: 12px;
      background: var(--moss);
      color: white;
      font-weight: bold;
      font-size: 1rem;
      cursor: pointer;
      box-shadow: 0 4px 12px var(--shadow);
      transition: transform 0.1s, filter 0.1s;
    }}
    button:active {{ transform: scale(0.98); filter: brightness(0.9); }}
    button.secondary {{ background: var(--clay); }}
    button.quiet {{ background: #7d8663; }}
    .small {{ color: #4d5b3b; font-size: .9rem; }}
    
    .scroll-box {{
      max-height: 250px;
      overflow-y: auto;
      border: 1px solid rgba(92, 111, 67, .3);
      padding: 15px;
      border-radius: 12px;
      background: rgba(255, 255, 255, 0.5);
    }}
  </style>
</head>
<body>
<main>
  <section class="hero">
    <span class="pill">Status: {{html.escape(status_label)}}</span>
    <h1>Pip's Digital Tavern</h1>
    <p>Your local assistant. Pip handles the small things so you don't have to.</p>
    <p style="margin-top:16px">
      <a href="/fairy"
         onclick="window.open('/fairy','pip-fairy','width=300,height=440,resizable=yes,menubar=no,toolbar=no,location=no');return false;"
         style="display:inline-block;background:var(--moss);color:white;text-decoration:none;
                border-radius:12px;padding:12px 24px;font-weight:bold;
                box-shadow:0 8px 18px var(--shadow);">
        ✦ Wake Pip
      </a>
    </p>
  </section>

  <section class="card">
    <h2>Current Thoughts</h2>
    <p><strong>{{html.escape(proposal_text)}}</strong></p>
    <div class="actions">
      <form method="post" action="/run-scan">
        <button type="submit">Run Memory Scan</button>
      </form>
      <form method="post" action="/run-ambient">
        <button class="quiet" type="submit">Start Ambient Loop</button>
      </form>
    </div>
  </section>

  <section class="card">
    <h2>App Integrations & Skills</h2>
    <p class="small" style="margin-bottom: 12px;">Select which applications Pip is allowed to interact with. She will gradually level up her skills for these apps.</p>
    <form method="post" action="/save-apps">
      <div class="scroll-box">
        {{apps_html}}
      </div>
      <div class="actions">
        <button type="submit">Save Integrations</button>
      </div>
    </form>
  </section>

  <section class="card">
    <h2>Linked Devices</h2>
    <p class="small">Connect your phone or tablet to allow Pip to assist you on the go.</p>
    <form method="post" action="/phone/usage-import">
      <p><textarea name="usage_json" placeholder="Paste device usage JSON here..." style="width:100%;height:60px;border-radius:8px;padding:8px;"></textarea></p>
      <div class="actions">
        <button class="secondary" type="submit">Sync Device</button>
      </div>
    </form>
  </section>

  <section class="card">
    <h2>Pip's Memory Folder</h2>
    <p>Pip stores all her thoughts, drafts, and JSON files in a dedicated local folder. You can safely open and edit these files at any time.</p>
    <p class="small">Folder: <code>PipMemory/</code></p>
  </section>
</main>
</body>
</html>"""

def fairy_page() -> str:'''

    new_content = content.replace(old_page, new_page)

    with open('pip_control_panel.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
        
    print("UI Overhauled!")

if __name__ == '__main__':
    run()
