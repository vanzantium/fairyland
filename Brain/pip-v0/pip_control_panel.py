#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from pip_phone_bridge import (
    apply_phone_feedback,
    get_phone_status,
    import_manual_summary_text,
    import_phone_usage_text,
)
from pip_pc_bridge import get_pc_status, import_pc_usage_text
from pip_workspace import (
    draft_next_actions,
    export_control_status,
    load_workspace,
    record_feedback,
    resolve_permission,
    run_ambient_cycle,
    queue_next_wake,
)
from pip_safety import request_safety_permission
import pip_app_skills
import pip_blender_recipes
import pip_jobs
import pip_platform
import pip_token_guard


class QuietThreadingHTTPServer(ThreadingHTTPServer):
    def handle_error(self, request: object, client_address: tuple[str, int]) -> None:
        # Mobile browsers sometimes close keep-alive sockets after a page transition.
        # That is normal and should not print a traceback that looks like a Pip failure.
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, BrokenPipeError, ConnectionAbortedError)):
            print(f"{client_address[0]} - connection closed by client")
            return
        super().handle_error(request, client_address)


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def page(status: dict[str, Any]) -> str:
    import json
    from pathlib import Path
    import html
    
    proposal = status.get("latest_proposal") or {}
    status_label = proposal.get("status", "idle")
    proposal_text = proposal.get("proposal", "Pip is resting. Tap Run Scan to wake her.")
    
    import pip_config
    memory_path = pip_config.get_memory_path()
    
    # Load apps
    apps = []
    try:
        with open(memory_path / "apps.json", "r", encoding="utf-8") as f:
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

    # Load hardware report
    hw = {}
    try:
        with open(memory_path / "hardware.json", "r", encoding="utf-8") as f:
            hw = json.load(f)
    except Exception:
        pass
        
    hw_html = ""
    if hw:
        rec = hw.get("recommendation", {})
        hw_html = f"""
        <div style="margin-top: 15px; padding: 10px; background: rgba(255,255,255,0.7); border-radius: 8px;">
            <p style="margin: 0 0 5px 0;"><strong>CPU:</strong> {html.escape(hw.get('cpu', ''))}</p>
            <p style="margin: 0 0 5px 0;"><strong>RAM:</strong> {hw.get('ram_gb', 0)} GB</p>
            <p style="margin: 0 0 5px 0;"><strong>GPU:</strong> {html.escape(hw.get('gpu', ''))}</p>
            <hr style="border: 0; border-top: 1px solid rgba(0,0,0,0.1); margin: 10px 0;">
            <p style="margin: 0 0 5px 0; color: #10b981; font-weight: bold;">Pip's Recommendation ({rec.get('tier', '')})</p>
            <p style="margin: 0 0 5px 0;"><strong>Model:</strong> {html.escape(rec.get('model', ''))}</p>
            <p style="margin: 0 0 5px 0; font-size: 0.9em; line-height: 1.4;">{html.escape(rec.get('reason', ''))}</p>
            <p style="margin: 0; font-size: 0.8em; font-style: italic; color: #666;">{html.escape(rec.get('prompt_strategy', ''))}</p>
        </div>
        """

    permissions = status.get("permissions") or {}
    pending_permissions = permissions.get("pending") or []
    if pending_permissions:
        permission_cards = []
        for item in pending_permissions:
            request_id = html.escape(item.get("id", ""))
            title = html.escape(item.get("title", "Permission request"))
            action_type = html.escape(item.get("action_type", "unknown"))
            rationale = html.escape(item.get("rationale", ""))
            permission_cards.append(f"""
            <div style="margin-bottom:12px;padding:12px;background:rgba(255,255,255,.62);border-radius:12px;border:1px solid rgba(92,111,67,.25);">
              <p style="margin:0 0 6px 0;"><strong>{title}</strong></p>
              <p class="small" style="margin:0 0 8px 0;">{action_type}: {rationale}</p>
              <form method="post" action="/permission" style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
                <input type="hidden" name="request_id" value="{request_id}">
                <input type="hidden" name="note" value="Resolved from Pip dashboard.">
                <button type="submit" name="decision" value="approved">Approve</button>
                <button class="secondary" type="submit" name="decision" value="denied">Deny</button>
              </form>
            </div>
            """)
        permissions_html = "\n".join(permission_cards)
    else:
        permissions_html = "<p class='small'>No pending permissions. Pip is staying inside her safe lane.</p>"

    jobs = pip_jobs.list_jobs().get("jobs", [])
    recent_jobs = list(reversed(jobs[-5:]))
    if recent_jobs:
        job_cards = []
        for job in recent_jobs:
            job_id = html.escape(job.get("id", ""))
            title = html.escape(job.get("title", "Untitled job"))
            kind = html.escape(job.get("kind", "job"))
            job_status = html.escape(job.get("status", "unknown"))
            latest_log = "<br>".join(html.escape(line) for line in job.get("latest_log", [])[-4:])
            stop_button = ""
            if job.get("status") in {"running", "stop_requested"}:
                stop_button = f"""
                <form method="post" action="/jobs/stop" style="margin-top:8px;">
                  <input type="hidden" name="job_id" value="{job_id}">
                  <button class="secondary" type="submit">Request Stop</button>
                </form>
                """
            job_cards.append(f"""
            <div style="margin-bottom:12px;padding:12px;background:rgba(255,255,255,.62);border-radius:12px;border:1px solid rgba(92,111,67,.25);">
              <p style="margin:0 0 6px 0;"><strong>{title}</strong></p>
              <p class="small" style="margin:0 0 8px 0;">{kind} | {job_status} | {job_id}</p>
              <div class="small" style="font-family:monospace;background:rgba(255,255,255,.65);padding:8px;border-radius:8px;min-height:32px;">{latest_log or "No log lines yet."}</div>
              {stop_button}
            </div>
            """)
        jobs_html = "\n".join(job_cards)
    else:
        jobs_html = "<p class='small'>No jobs yet. Approved autonomous goals will show up here.</p>"

    blender = pip_app_skills.assess_app("Blender")
    blender_summary = blender.get("summary", {})
    blender_domains = blender.get("app", {}).get("domains", {})
    blender_domain_html = ""
    for domain_key, domain in blender_domains.items():
        blender_domain_html += f"""
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;gap:12px;">
          <span>{html.escape(domain.get('label', domain_key))}</span>
          <span class="small" style="background:var(--leaf);padding:2px 6px;border-radius:4px;">Lvl {domain.get('level', 1)} ({domain.get('xp', 0)}xp)</span>
        </div>
        """
    blender_focus = "".join(f"<li>{html.escape(step)}</li>" for step in blender_summary.get("next_focus", []))
    if not blender_focus:
        blender_focus = "<li>Record a Blender action to build Pip's first evidence trail.</li>"

    blender_recipes = pip_blender_recipes.list_recipes()
    recipe_buttons = ""
    for recipe in blender_recipes.get("recipes", [])[:5]:
        key = html.escape(recipe.get("key", ""))
        title = html.escape(recipe.get("title", key))
        domain = html.escape(recipe.get("domain", "general"))
        intent = html.escape(recipe.get("intent", ""))
        recipe_buttons += f"""
        <form method="post" action="/blender/recipe-draft" style="margin-bottom:10px;padding:10px;background:rgba(255,255,255,.55);border-radius:12px;">
          <input type="hidden" name="recipe" value="{key}">
          <input type="hidden" name="project" value="Blender practice">
          <p style="margin:0 0 4px 0;"><strong>{title}</strong></p>
          <p class="small" style="margin:0 0 8px 0;">{domain}: {intent}</p>
          <button type="submit">Draft This Recipe</button>
        </form>
        """
    latest_recipe = ""
    history = blender_recipes.get("history", [])
    if history:
        item = history[-1]
        latest_recipe = f"""
        <p class="small"><strong>Latest draft:</strong> {html.escape(item.get('title', 'Recipe'))} | {html.escape(item.get('status', 'drafted'))}</p>
        <p class="small" style="word-break:break-all;">{html.escape(item.get('path', ''))}</p>
        """
    else:
        latest_recipe = "<p class='small'>No Blender recipes drafted yet.</p>"

    governor = pip_token_guard.status()
    gov_pct = int(governor.get("remaining_ratio", 0) * 100)
    gov_mode = html.escape(governor.get("mode", "BUILD"))
    gov_last = governor.get("last_assessment") or {}
    gov_nudge = html.escape(gov_last.get("nudge") or "Pip is watching the budget and will nudge when work gets wasteful.")
    gov_signal = html.escape((gov_last.get("signal") or {}).get("triage_summary", "No recent Signal Sieve assessment."))
    gov_events = ""
    for event in governor.get("recent_events", [])[-5:]:
        gov_events += f"""
        <div class="small" style="display:flex;justify-content:space-between;gap:8px;margin-bottom:4px;">
          <span>{html.escape(event.get('intent', 'event'))}</span>
          <span>{event.get('actual_tokens', 0)} spent / {event.get('saved_tokens', 0)} saved</span>
        </div>
        """
    if not gov_events:
        gov_events = "<p class='small'>No token events recorded yet.</p>"

    platform_status = pip_platform.feature_status()
    platform_features = platform_status.get("features", {})
    platform_html = ""
    for feature, enabled in platform_features.items():
        label = feature.replace("_", " ").title()
        platform_html += f"""
        <div class="small" style="display:flex;justify-content:space-between;gap:8px;margin-bottom:4px;">
          <span>{html.escape(label)}</span>
          <span>{'available' if enabled else 'not yet'}</span>
        </div>
        """

    developer_shells = pip_app_skills.inspect_developer_shells().get("shells", [])
    shell_cards = ""
    for shell in developer_shells:
        domains = shell.get("domains", {})
        domain_labels = ", ".join(
            domain.get("label", key.replace("_", " ").title())
            for key, domain in list(domains.items())[:3]
        )
        guidance = shell.get("handoff_guidance", ["Keep handoffs scoped and permission-gated."])[0]
        shell_cards += f"""
        <div style="margin-bottom:12px;padding:12px;background:rgba(255,255,255,.62);border-radius:12px;border:1px solid rgba(92,111,67,.25);">
          <p style="margin:0 0 6px 0;"><strong>{html.escape(shell.get('name', 'Developer Shell'))}</strong></p>
          <p class="small" style="margin:0 0 6px 0;">Lvl {shell.get('level', 1)} ({shell.get('xp', 0)}xp) | persona: {html.escape(shell.get('persona', ''))}</p>
          <p class="small" style="margin:0 0 6px 0;">{html.escape(shell.get('role', 'developer tool'))}</p>
          <p class="small" style="margin:0;">{html.escape(domain_labels or guidance)}</p>
        </div>
        """
    if not shell_cards:
        shell_cards = "<p class='small'>Developer shells have not been bootstrapped yet.</p>"

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
        radial-gradient(circle at top left, rgba(16, 185, 129, 0.4), transparent 32rem),
        linear-gradient(140deg, #0f172a 0%, #1e1b4b 54%, #064e3b 100%);
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
    <h2>Autonomous Mode</h2>
    <p class="small">Queue a long-running goal for review. Pip will not start autonomous work until you approve it.</p>
    <form method="post" action="/run-goal">
      <p><input type="text" name="goal_text" placeholder="e.g. Read the brain folder and summarize..." style="width:100%; border-radius:8px; padding:10px; border:1px solid rgba(92,111,67,.3); font-family:inherit;"></p>
      <div class="actions">
        <button type="submit" style="background: var(--clay);">Request Autonomous Goal</button>
      </div>
    </form>
  </section>

  <section class="card">
    <h2>Token Governor</h2>
    <span class="pill">Mode: {gov_mode}</span>
    <span class="pill">Daily remaining: {gov_pct}%</span>
    <p class="small">{gov_nudge}</p>
    <p class="small"><strong>Signal bridge:</strong> {gov_signal}</p>
    <div class="scroll-box" style="max-height:150px;">
      {gov_events}
    </div>
  </section>

  <section class="card">
    <h2>Platform Fit</h2>
    <span class="pill">OS: {html.escape(platform_status.get('os', 'Unknown'))}</span>
    <p class="small">Pip's brain is cross-platform; some body features depend on OS permissions and adapters.</p>
    <div class="scroll-box" style="max-height:180px;">
      {platform_html}
    </div>
  </section>

  <section class="card">
    <h2>Developer Shells</h2>
    <p class="small">Starter shells for supervised handoffs into coding assistants. Pip can prepare the task; actual UI handoff remains approval-gated.</p>
    <form method="post" action="/developer-shells/bootstrap" style="margin-bottom:12px;">
      <button class="quiet" type="submit">Bootstrap Developer Shells</button>
    </form>
    <div class="scroll-box" style="max-height:280px;">
      {shell_cards}
    </div>
  </section>

  <section class="card">
    <h2>Permission Queue</h2>
    <p class="small">High-risk actions wait here before Pip can touch apps, run scripts, or start autonomous work.</p>
    {permissions_html}
  </section>

  <section class="card">
    <h2>Running Jobs</h2>
    <p class="small">Approved long-running work appears here with recent logs and cooperative stop controls.</p>
    {jobs_html}
  </section>

  <section class="card">
    <h2>Blender Skill Track</h2>
    <p class="small">Pip's starter path toward becoming a tiny animation-team assistant.</p>
    <p><strong>Level {blender_summary.get('level', 1)}</strong> | {blender_summary.get('xp', 0)}xp | {html.escape(blender_summary.get('role', 'app teammate'))}</p>
    <div class="scroll-box" style="max-height:220px;margin-bottom:12px;">
      {blender_domain_html}
    </div>
    <p class="small"><strong>Next focus:</strong></p>
    <ul class="small">{blender_focus}</ul>
    <form method="post" action="/app-skills/award">
      <input type="hidden" name="app" value="Blender">
      <input type="hidden" name="domain" value="navigation">
      <input type="hidden" name="amount" value="10">
      <input type="hidden" name="evidence" value="Manual Blender practice/check-in from dashboard.">
      <button type="submit">Log Blender Practice</button>
    </form>
  </section>

  <section class="card">
    <h2>Blender Recipe Lab</h2>
    <p class="small">Draft-only task recipes. Pip writes plans into memory first; execution still needs separate approval.</p>
    {latest_recipe}
    <div class="scroll-box" style="max-height:360px;">
      {recipe_buttons}
    </div>
  </section>

  <section class="card">
    <h2>My Apps</h2>
    <p class="small" style="margin-bottom: 12px;">Select which applications Pip is allowed to interact with. She will gradually learn and level up as you use them together!</p>
    
    <form method="post" action="/apps/scan" style="margin-bottom: 15px;">
      <button type="submit" style="background: var(--clay);">🔍 Scan Computer for Installed Apps</button>
    </form>
    
    <form method="post" action="/save-apps">
      <div class="scroll-box" style="margin-bottom: 15px;">
        {apps_html}
      </div>
      <div class="actions">
        <button type="submit">Save Allowed Apps</button>
      </div>
    </form>
  </section>

  <section class="card">
    <h2>System Diagnosis & Optimization</h2>
    <p>Pip can scan your PC's hardware and recommend the safest Ollama model. Memory cleanup is now separated from normal scans so status checks stay gentle.</p>
    <form method="post" action="/hardware/scan">
      <div class="actions">
        <button class="secondary" type="submit">Run Hardware Scan</button>
      </div>
    </form>
    {hw_html}
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
    <div style="background: rgba(255,255,255,0.6); padding: 10px; border-radius: 8px; border: 1px solid rgba(92,111,67,0.3); font-family: monospace; word-break: break-all; margin-bottom: 15px;">
      {html.escape(str(memory_path))}
    </div>
    <form method="post" action="/select-folder">
      <div class="actions">
        <button class="secondary" type="submit">Browse for Folder...</button>
      </div>
    </form>
  </section>
</main>
</body>
</html>"""

def fairy_page() -> str:
    from pathlib import Path
    has_avatar = False
    for ext in ["png", "jpg", "jpeg", "gif"]:
        if Path(f"avatar.{ext}").exists():
            has_avatar = True
            break

    if has_avatar:
        sprite_html = '<img class="sprite" id="fairy" src="/avatar" width="112" height="179" style="object-fit: contain; filter: drop-shadow(0 5px 14px rgba(16,185,129,0.5));" onclick="tap()">'
    else:
        sprite_html = """<svg class="sprite" id="fairy" viewBox="0 0 100 140" width="112" height="179" onclick="tap()">
    <defs>
      <radialGradient id="hgrad" cx="50%" cy="50%" r="50%">
        <stop offset="0%" stop-color="#fff" stop-opacity=".9"/>
        <stop offset="60%" stop-color="#fff" stop-opacity=".7"/>
        <stop offset="100%" stop-color="#fff" stop-opacity="0"/>
      </radialGradient>
    </defs>
    
    <!-- back wings -->
    <path class="wll" d="M47 89 Q22 60 10 75 Q28 105 47 89" fill="rgba(16,185,129,.5)"/>
    <path class="wrl" d="M53 89 Q78 60 90 75 Q72 105 53 89" fill="rgba(139,92,246,.5)"/>

    <!-- front wings -->
    <path class="wl" d="M47 82 Q15 45 4 64 Q25 100 47 82" fill="rgba(16,185,129,.8)"/>
    <path class="wr" d="M53 82 Q85 45 96 64 Q75 100 53 82" fill="rgba(139,92,246,.8)"/>

    <!-- body/dress -->
    <path d="M45 80 Q35 110 32 125 Q50 135 68 125 Q65 110 55 80 Z" fill="#8b5cf6"/>
    <path d="M47 80 Q39 110 36 123 Q50 130 64 123 Q61 110 53 80 Z" fill="#6d28d9"/>

    <!-- head -->
    <circle cx="50" cy="72" r="13.5" fill="url(#hgrad)"/>

    <!-- leaf crown -->
    <path d="M37 65 C35 54 43 50 46 61" fill="#0f172a" opacity=".95"/>
    <path d="M42 62 C41 51 51 48 51 60" fill="#1e1b4b" opacity=".95"/>
    <path d="M50 61 C51 50 61 50 60 61" fill="#0f172a" opacity=".95"/>
    <path d="M56 64 C60 54 66 55 64 64" fill="#1e1b4b" opacity=".9"/>
    <!-- crown highlight -->
    <path d="M38 64 C36 55 43 52 46 60" fill="rgba(16,185,129,.3)"/>
    <path d="M51 61 C52 52 60 52 59 61" fill="rgba(16,185,129,.3)"/>

    <!-- eyes -->
    <circle cx="45" cy="73" r="2.4" fill="#0d1810"/>
    <circle cx="55" cy="73" r="2.4" fill="#0d1810"/>
    <circle cx="45.9" cy="72.2" r=".9" fill="white"/>
    <circle cx="55.9" cy="72.2" r=".9" fill="white"/>

    <!-- blush -->
    <ellipse cx="41.5" cy="77" rx="3.2" ry="1.6" fill="rgba(139,92,246,.5)"/>
    <ellipse cx="58.5" cy="77" rx="3.2" ry="1.6" fill="rgba(139,92,246,.5)"/>

    <!-- smile -->
    <path d="M45.5 78 Q50 82 54.5 78" stroke="#0d1810" stroke-width="1.3"
          fill="none" stroke-linecap="round"/>

    <!-- legs -->
    <line x1="46" y1="116" x2="43" y2="133" stroke="#312e81" stroke-width="2.6" stroke-linecap="round"/>
    <line x1="54" y1="116" x2="57" y2="133" stroke="#312e81" stroke-width="2.6" stroke-linecap="round"/>
    <ellipse cx="42"  cy="134.5" rx="5.5" ry="2.2" fill="#312e81"/>
    <ellipse cx="58"  cy="134.5" rx="5.5" ry="2.2" fill="#312e81"/>
  </svg>"""

    html_str = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Pip</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    :root{
      --moss:#8b5cf6;--leaf:#10b981;--silk:#0f172a;
      --clay:#f59e0b;--ink:#e0e6ff;--quiet:#94a3b8;
    }
    html,body{
      height:100%;overflow:hidden;
      font-family:Georgia,"Times New Roman",serif;
      background:
        radial-gradient(circle at 30% 20%,rgba(16,185,129,.5),transparent 60%),
        linear-gradient(160deg,#0f172a 0%,#1e1b4b 60%,#064e3b 100%);
      -webkit-app-region:drag;
      -webkit-user-select:none;user-select:none;
    }
    body{
      display:flex;flex-direction:column;
      align-items:center;justify-content:center;
      min-height:100vh;padding:16px;
    }
    /* close btn */
    .closebtn{
      position:fixed;top:8px;left:10px;
      width:20px;height:20px;border-radius:50%;
      background:rgba(92,111,67,.22);border:0;
      cursor:pointer;font-size:11px;line-height:20px;text-align:center;
      color:var(--quiet);transition:background .15s;
      -webkit-app-region:no-drag;
    }
    .closebtn:hover{background:rgba(185,111,77,.5);color:#fff;}

    /* stage */
    .stage{position:relative;display:flex;flex-direction:column;align-items:center;}

    /* speech bubble */
    .bubble{
      width:252px;
      background:rgba(30,41,59,.92);
      border:1.5px solid rgba(16,185,129,.4);
      border-radius:22px;
      padding:14px 15px 12px;
      box-shadow:0 6px 28px rgba(139,92,246,.4);
      margin-bottom:12px;
      display:none;
      animation:bubble-in .38s cubic-bezier(.34,1.56,.64,1) both;
      -webkit-app-region:no-drag;
    }
    .bubble::after{
      content:"";display:block;
      width:0;height:0;margin:8px auto 0;
      border:10px solid transparent;
      border-top-color:rgba(30,41,59,.92);
    }
    .show .bubble{display:block;}

    @keyframes bubble-in{
      from{opacity:0;transform:scale(.88) translateY(8px);}
      to  {opacity:1;transform:scale(1)   translateY(0);}
    }

    .prop{font-size:.88rem;color:var(--ink);line-height:1.44;margin-bottom:7px;font-weight:700;}
    .evid{font-size:.76rem;color:#94a3b8;line-height:1.32;margin-bottom:11px;}

    .btns{display:flex;gap:7px;}
    .btn{
      flex:1;border:0;border-radius:14px;padding:9px 4px;
      cursor:pointer;font:700 .74rem Georgia,serif;
      transition:filter .14s,transform .1s;
    }
    .btn:active{filter:brightness(.86);transform:scale(.95);}
    .yes {background:var(--moss);color:#fff;}
    .wait{background:var(--quiet);color:#fff;}
    .no  {background:var(--clay);color:#fff;}

    /* idle dots */
    .idle{display:flex;gap:5px;margin-top:8px;height:14px;align-items:center;}
    .show .idle{visibility:hidden;}
    .d{
      width:6px;height:6px;border-radius:50%;
      background:var(--leaf);animation:bounce 1.5s ease-in-out infinite;opacity:.8;
    }
    .d:nth-child(2){animation-delay:.22s;}
    .d:nth-child(3){animation-delay:.44s;}
    @keyframes bounce{
      0%,80%,100%{transform:translateY(0);opacity:.35;}
      40%{transform:translateY(-5px);opacity:.9;}
    }

    /* fairy float */
    .sprite{
      animation:float 3.6s ease-in-out infinite;
      filter:drop-shadow(0 5px 14px rgba(55,75,35,.25));
      cursor:pointer;
    }
    @keyframes float{
      0%,100%{transform:translateY(0);}
      50%    {transform:translateY(-11px);}
    }
    @keyframes pop{
      0%,100%{transform:translateY(0) rotate(0);}
      25%    {transform:translateY(-4px) rotate(-5deg);}
      75%    {transform:translateY(-4px) rotate(5deg);}
    }
    .popping .sprite{animation:float 3.6s ease-in-out infinite,pop .5s ease-in-out;}

    /* wings */
    .wl {transform-origin:47px 82px;animation:wf 1.1s ease-in-out infinite;}
    .wr {transform-origin:53px 82px;animation:wf 1.1s ease-in-out infinite .08s;}
    .wll{transform-origin:47px 89px;animation:wf 1.3s ease-in-out infinite .15s;}
    .wrl{transform-origin:53px 89px;animation:wf 1.3s ease-in-out infinite .23s;}
    @keyframes wf{
      0%,100%{transform:scaleX(1);}
      50%    {transform:scaleX(.8);}
    }

    /* sparkles */
    .sp{
      position:absolute;border-radius:50%;
      background:var(--leaf);pointer-events:none;
      opacity:0;transition:opacity .4s;
    }
    .show .sp{animation:sparkle 2.2s ease-in-out infinite;}
    @keyframes sparkle{
      0%,100%{opacity:0;transform:scale(.4);}
      50%    {opacity:.75;transform:scale(1.1);}
    }

    /* status dot */
    .badge{
      position:fixed;top:10px;right:10px;
      width:9px;height:9px;border-radius:50%;
      background:var(--moss);animation:pulse 2.2s ease-in-out infinite;
    }
    .show ~ .badge,.show+.badge{background:var(--clay);}
    @keyframes pulse{
      0%,100%{opacity:1;transform:scale(1);}
      50%    {opacity:.35;transform:scale(.65);}
    }

    /* full panel link */
    .fulllink{
      position:fixed;bottom:10px;
      font-size:.7rem;color:var(--quiet);
      text-decoration:none;opacity:.5;
      -webkit-app-region:no-drag;
    }
    .fulllink:hover{opacity:1;}
  </style>
</head>
<body>

<div id="root" class="stage">

  <div class="bubble">
    <p class="prop" id="ptxt">…</p>
    <p class="evid" id="etxt"></p>
    <div class="btns">
      <button class="btn yes"  onclick="fb('accepted')">Accept</button>
      <button class="btn wait" onclick="fb('deferred')">Later</button>
      <button class="btn no"   onclick="fb('rejected')">Nope</button>
    </div>
  </div>

  <!-- sparkles (activate via .show on parent) -->
  <div class="sp" style="width:7px;height:7px;top:4px;left:22px;animation-delay:0s"></div>
  <div class="sp" style="width:5px;height:5px;top:18px;right:20px;animation-delay:.8s"></div>
  <div class="sp" style="width:6px;height:6px;top:-4px;right:38px;animation-delay:1.5s"></div>

  __SPRITE_HTML__

  <!-- idle breathing dots -->
  <div class="idle">
    <div class="d"></div><div class="d"></div><div class="d"></div>
  </div>

  <div id="chatbox" style="display:none; width: 280px; margin-top: 15px; background: rgba(251,248,234,.9); border-radius: 12px; padding: 10px; box-shadow: 0 4px 12px rgba(28,36,23,.1); -webkit-app-region:no-drag; position:relative; z-index: 10;">
    <div id="chatlog" style="height: 120px; overflow-y: auto; font-size: 0.8rem; margin-bottom: 8px; display: flex; flex-direction: column; gap: 4px; user-select: text; -webkit-user-select: text; cursor: auto;"></div>
    <div style="display: flex; gap: 5px;">
      <input type="text" id="chatinput" placeholder="Say hi..." style="flex: 1; border: 1px solid rgba(92,111,67,.3); border-radius: 8px; padding: 6px; box-sizing: border-box; font-family: inherit; font-size: 0.8rem;" onkeydown="if(event.key === 'Enter') sendChat()">
      <label for="chatfile" style="cursor: pointer; background: rgba(92,111,67,.1); border-radius: 8px; padding: 6px 10px; display: flex; align-items: center; justify-content: center; font-size: 0.8rem;" title="Attach a text file">📎</label>
      <input type="file" id="chatfile" style="display: none;">
    </div>
  </div>

</div>

<button class="closebtn" onclick="closePip()" title="Hide Pip">✕</button>
<button class="chatbtn" onclick="toggleChat()" title="Chat with Pip" style="position:fixed;top:8px;left:35px;width:20px;height:20px;border-radius:50%;background:rgba(92,111,67,.22);border:0;cursor:pointer;font-size:11px;line-height:20px;text-align:center;color:var(--quiet);transition:background .15s;-webkit-app-region:no-drag;">💬</button>
<div class="badge" id="badge"></div>
<a class="fulllink" href="/" target="_blank" style="left:10px;">open full panel</a>

<script>
  async function uploadAvatar() {
    const file = document.getElementById('avatar_file').files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async function() {
      const b64 = reader.result.split(',')[1];
      await fetch('/upload-avatar', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({image: b64, filename: file.name})
      });
      location.reload();
    };
    reader.readAsDataURL(file);
  }

  const root  = document.getElementById('root');
  const badge = document.getElementById('badge');

  async function revertAvatar() {
    await fetch('/revert-avatar', {method: 'POST'});
    location.reload();
  }

  async function poll() {
    try {
      const d = await fetch('/pip/latest').then(r => r.json());
      const live = d && d.proposal
                   && d.status !== 'accepted'
                   && d.status !== 'rejected'
                   && d.status !== 'none';
      if (live) {
        document.getElementById('ptxt').textContent = d.proposal  || '';
        document.getElementById('etxt').textContent = d.evidence  || '';
        root.classList.add('show');
        badge.style.background = 'var(--clay)';
      } else {
        root.classList.remove('show');
        badge.style.background = 'var(--moss)';
      }
    } catch(_) {}
  }

  async function fb(status) {
    root.classList.remove('show');
    badge.style.background = 'var(--moss)';
    try {
      await fetch('/feedback', {
        method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: 'status=' + status + '&note='
      });
    } catch(_) {}
  }

  function tap() {
    root.classList.add('popping');
    setTimeout(() => root.classList.remove('popping'), 520);
    poll();
  }

  function toggleChat() {
    const cb = document.getElementById('chatbox');
    cb.style.display = cb.style.display === 'none' ? 'block' : 'none';
  }

  async function sendChat() {
    const inp = document.getElementById('chatinput');
    const finp = document.getElementById('chatfile');
    let txt = inp.value.trim();
    let displayTxt = txt;
    
    if (finp.files.length > 0) {
      try {
        const file = finp.files[0];
        const content = await file.text();
        txt += "\\n\\n[Attached File: " + file.name + "]\\n" + content;
        displayTxt += " [📎 " + file.name + "]";
        finp.value = "";
      } catch (e) {
        console.error("Failed to read file", e);
      }
    }
    
    if (!txt) return;
    inp.value = '';
    
    const log = document.getElementById('chatlog');
    const umsg = document.createElement('div');
    umsg.textContent = "You: " + displayTxt;
    umsg.style.alignSelf = "flex-end";
    umsg.style.color = "var(--moss)";
    log.appendChild(umsg);
    log.scrollTop = log.scrollHeight;

    try {
      const res = await fetch('/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: 'msg=' + encodeURIComponent(txt)
      }).then(r => r.json());

      const pmsg = document.createElement('div');
      pmsg.textContent = "Pip: " + (res.response || "...");
      pmsg.style.alignSelf = "flex-start";
      pmsg.style.fontWeight = "bold";
      log.appendChild(pmsg);
      log.scrollTop = log.scrollHeight;
    } catch(e) {}
  }

  poll();
  setInterval(poll, 30000);

  function closePip() {
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.hide_window();
    } else {
      window.close();
    }
  }
</script>
</body>
</html>"""
    return html_str.replace("__SPRITE_HTML__", sprite_html)


class PipHandler(BaseHTTPRequestHandler):
    workspace_key = "garden_spiders"
    manifest_path = "approved_workspaces.json"

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")

    def send_json(self, payload: Any, status: int = 200) -> None:
        encoded = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def redirect_home(self) -> None:
        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()

    def read_body(self) -> dict[str, list[str]]:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8") if length else ""
        return parse_qs(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/":
                status = export_control_status(self.workspace_key, self.manifest_path)
                encoded = page(status).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
            elif parsed.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
            elif parsed.path == "/status":
                self.send_json(export_control_status(self.workspace_key, self.manifest_path))
            elif parsed.path == "/apps":
                import pip_evolution
                self.send_json(pip_evolution.load_apps())
            elif parsed.path == "/proposal/latest":
                status = export_control_status(self.workspace_key, self.manifest_path)
                self.send_json(status.get("latest_proposal") or {})
            elif parsed.path == "/memory/latest":
                status = export_control_status(self.workspace_key, self.manifest_path)
                self.send_json(status.get("latest_memory") or {})
            elif parsed.path == "/ambient/latest":
                status = export_control_status(self.workspace_key, self.manifest_path)
                self.send_json(status.get("ambient") or {})
            elif parsed.path == "/permissions":
                status = export_control_status(self.workspace_key, self.manifest_path)
                self.send_json(status.get("permissions") or {})
            elif parsed.path == "/jobs":
                self.send_json(pip_jobs.list_jobs())
            elif parsed.path == "/app-skills":
                self.send_json(pip_app_skills.list_profiles())
            elif parsed.path == "/developer-shells":
                self.send_json(pip_app_skills.inspect_developer_shells())
            elif parsed.path == "/blender/recipes":
                self.send_json(pip_blender_recipes.list_recipes())
            elif parsed.path == "/token-governor":
                self.send_json(pip_token_guard.status())
            elif parsed.path == "/platform":
                self.send_json(pip_platform.feature_status())
            elif parsed.path == "/phone/status":
                self.send_json(get_phone_status())
            elif parsed.path == "/pc/status":
                self.send_json(get_pc_status())
            elif parsed.path == "/default-fairy":
                try:
                    with open("default_fairy.png", "rb") as f:
                        self.send_response(200)
                        self.send_header("Content-Type", "image/png")
                        self.send_header("Content-Length", str(Path("default_fairy.png").stat().st_size))
                        self.end_headers()
                        self.wfile.write(f.read())
                except Exception:
                    self.send_json({"error": "not found"}, status=404)
            elif parsed.path == "/avatar":
                from pathlib import Path
                avatar_path = None
                for ext in ["png", "jpg", "jpeg", "gif"]:
                    p = Path(f"avatar.{ext}")
                    if p.exists():
                        avatar_path = p
                        break
                if avatar_path:
                    self.send_response(200)
                    self.send_header("Content-Type", f"image/{avatar_path.suffix[1:]}")
                    self.send_header("Content-Length", str(avatar_path.stat().st_size))
                    self.end_headers()
                    with open(avatar_path, "rb") as f:
                        self.wfile.write(f.read())
                else:
                    self.send_json({"error": "not found"}, status=404)
            elif parsed.path == "/pip/latest":
                # Combined endpoint: workspace proposal OR phone proposal, whichever is active
                status = export_control_status(self.workspace_key, self.manifest_path)
                wp = status.get("latest_proposal") or {}
                phone = get_phone_status()
                phone_proposal = phone.get("proposal") or {}
                phone_card = phone_proposal.get("proposal_card") or phone_proposal
                pc = get_pc_status()
                pc_proposal = pc.get("proposal") or {}
                pc_card = pc_proposal.get("proposal_card") or pc_proposal
                # Prefer workspace proposal if it has text; fall back to phone
                if wp.get("proposal"):
                    self.send_json(wp)
                elif phone_card.get("proposal"):
                    self.send_json(phone_card)
                elif pc_card.get("proposal"):
                    self.send_json(pc_card)
                else:
                    self.send_json({})
            elif parsed.path == "/fairy":
                encoded = fairy_page().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
            else:
                self.send_json({"error": "not found"}, status=404)
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=500)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/run-scan":
                draft_next_actions(self.workspace_key, self.manifest_path)
                self.redirect_home()
            elif parsed.path == "/run-goal":
                form = self.read_body()
                goal_text = form.get("goal_text", [""])[0]
                if goal_text:
                    assessment = pip_token_guard.assess_interaction(
                        goal_text,
                        intent="autonomous_goal",
                        source_type="first_hand",
                        source_name="Pip dashboard goal",
                    )
                    if assessment["allowed"]:
                        request_safety_permission(
                            "autonomous_goal",
                            title="Approve autonomous Pip goal",
                            rationale=goal_text,
                            workspace_key=self.workspace_key,
                            manifest_path=self.manifest_path,
                            details={"goal": goal_text, "source": "dashboard", "token_governor": assessment},
                        )
                    else:
                        pip_token_guard.record_event(
                            "autonomous_goal",
                            estimated_tokens=assessment["estimated_tokens"],
                            actual_tokens=0,
                            saved_tokens=assessment["estimated_tokens"],
                            note=f"Blocked by Token Governor: {assessment['reason']}",
                        )
                self.redirect_home()
            elif parsed.path == "/apps/scan":
                import pip_app_scanner
                pip_app_scanner.scan_and_save()
                self.redirect_home()
            elif parsed.path == "/hardware/scan":
                import pip_hardware_scanner
                pip_hardware_scanner.scan_and_save(optimize=False)
                self.redirect_home()
            elif parsed.path == "/developer-shells/bootstrap":
                pip_app_skills.bootstrap_developer_shells(write_personas=True)
                self.redirect_home()
            elif parsed.path == "/save-apps":
                form = self.read_body()
                import pip_evolution
                apps = pip_evolution.load_apps()
                for app in apps:
                    field_name = f"app_{app['name']}"
                    app['enabled'] = field_name in form
                pip_evolution.save_apps(apps)
                self.redirect_home()
            elif parsed.path == "/select-folder":
                if not pip_platform.is_windows():
                    # Folder picking is Windows-only for now; config can still be edited directly.
                    self.redirect_home()
                    return
                import subprocess
                ps_script = """
Add-Type -AssemblyName System.windows.forms
$f = New-Object System.Windows.Forms.FolderBrowserDialog
$f.Description = "Select Pip's Memory Folder"
$f.ShowNewFolderButton = $true
if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
    Write-Output $f.SelectedPath
}
"""
                try:
                    out = subprocess.check_output(
                        ["powershell", "-NoProfile", "-Command", ps_script],
                        text=True,
                        **pip_platform.hidden_subprocess_kwargs(),
                    ).strip()
                    if out:
                        import pip_config
                        pip_config.set_memory_path(out)
                except Exception as e:
                    print(f"Folder selection error: {e}")
                self.redirect_home()
            elif parsed.path == "/run-ambient":
                context = "Phone-triggered Garden Spiders ambient cycle."
                assessment = pip_token_guard.assess_interaction(context, intent="ambient_cycle")
                if assessment["allowed"]:
                    run_ambient_cycle(self.workspace_key, 30, context, self.manifest_path)
                    pip_token_guard.record_event("ambient_cycle", estimated_tokens=assessment["estimated_tokens"])
                else:
                    pip_token_guard.record_event(
                        "ambient_cycle",
                        estimated_tokens=assessment["estimated_tokens"],
                        actual_tokens=0,
                        saved_tokens=assessment["estimated_tokens"],
                        note=f"Blocked by Token Governor: {assessment['reason']}",
                    )
                self.redirect_home()
            elif parsed.path == "/schedule":
                queue_next_wake(self.workspace_key, 30, "Phone-scheduled Garden Spiders ambient cycle.", self.manifest_path)
                self.redirect_home()
            elif parsed.path == "/feedback":
                form = self.read_body()
                status = (form.get("status") or [""])[0]
                note = (form.get("note") or [""])[0]
                record_feedback(self.workspace_key, status, note, self.manifest_path)
                self.redirect_home()
            elif parsed.path == "/permission":
                form = self.read_body()
                request_id = (form.get("request_id") or [""])[0]
                decision = (form.get("decision") or [""])[0]
                note = (form.get("note") or [""])[0]
                resolved = resolve_permission(self.workspace_key, request_id, decision, note, self.manifest_path)
                if decision == "approved" and resolved.get("action_type") == "autonomous_goal":
                    goal_text = (resolved.get("details") or {}).get("goal") or resolved.get("rationale", "")
                    if goal_text:
                        pip_jobs.start_autonomous_goal(goal_text)
                self.redirect_home()
            elif parsed.path == "/jobs/stop":
                form = self.read_body()
                job_id = (form.get("job_id") or [""])[0]
                pip_jobs.request_stop(job_id)
                self.redirect_home()
            elif parsed.path == "/app-skills/award":
                form = self.read_body()
                pip_app_skills.award_app_xp(
                    (form.get("app") or ["Blender"])[0],
                    int((form.get("amount") or ["10"])[0]),
                    domain=(form.get("domain") or ["general"])[0],
                    evidence=(form.get("evidence") or [""])[0],
                )
                self.redirect_home()
            elif parsed.path == "/blender/recipe-draft":
                form = self.read_body()
                recipe = (form.get("recipe") or ["simple_character_blockout"])[0]
                project = (form.get("project") or ["Blender practice"])[0]
                goal = (form.get("goal") or [""])[0]
                assessment = pip_token_guard.assess_interaction(
                    f"{project} {recipe} {goal}",
                    intent="blender_recipe",
                    source_type="first_hand",
                    source_name="Pip Blender Recipe Lab",
                )
                if assessment["allowed"]:
                    pip_blender_recipes.draft_recipe(recipe, project=project, goal=goal)
                    pip_token_guard.record_event("blender_recipe", estimated_tokens=assessment["estimated_tokens"])
                else:
                    pip_token_guard.record_event(
                        "blender_recipe",
                        estimated_tokens=assessment["estimated_tokens"],
                        actual_tokens=0,
                        saved_tokens=assessment["estimated_tokens"],
                        note=f"Blocked by Token Governor: {assessment['reason']}",
                    )
                self.redirect_home()
            elif parsed.path == "/phone/usage-import":
                content_type = self.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    length = int(self.headers.get("Content-Length", "0"))
                    usage_json = self.rfile.read(length).decode("utf-8") if length else ""
                else:
                    form = self.read_body()
                    usage_json = (form.get("usage_json") or [""])[0]
                import_phone_usage_text(usage_json, "dashboard_upload.json", run_optimizer=True)
                self.redirect_home()
            elif parsed.path == "/pc/usage-import":
                content_type = self.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    length = int(self.headers.get("Content-Length", "0"))
                    usage_json = self.rfile.read(length).decode("utf-8") if length else ""
                else:
                    form = self.read_body()
                    usage_json = (form.get("usage_json") or [""])[0]
                import_pc_usage_text(usage_json, "pc_dashboard_upload.json", run_optimizer=True)
                self.redirect_home()
            elif parsed.path == "/phone/summary-import":
                form = self.read_body()
                summary_csv = (form.get("summary_csv") or [""])[0]
                import_manual_summary_text(summary_csv, "dashboard_manual_summary.csv")
                self.redirect_home()
            elif parsed.path == "/phone/feedback":
                form = self.read_body()
                feedback = (form.get("feedback") or [""])[0]
                note = (form.get("note") or [""])[0]
                apply_phone_feedback(feedback, note)
                self.redirect_home()
            elif parsed.path == "/chat":
                form = self.read_body()
                msg = (form.get("msg") or [""])[0]
                assessment = pip_token_guard.assess_interaction(
                    msg,
                    intent="chat",
                    source_type="first_hand",
                    source_name="Pip dashboard chat",
                )
                if not assessment["allowed"]:
                    pip_token_guard.record_event(
                        "chat",
                        estimated_tokens=assessment["estimated_tokens"],
                        actual_tokens=0,
                        saved_tokens=assessment["estimated_tokens"],
                        note=f"Blocked by Token Governor: {assessment['reason']}",
                    )
                    self.send_json({"response": assessment["nudge"], "token_governor": assessment})
                    return
                from pip_engine import PipEngine
                engine = PipEngine()
                try:
                    response = engine.generate_chat_response(msg)
                except Exception:
                    response = "I'm having trouble processing that right now."
                pip_token_guard.record_event(
                    "chat",
                    estimated_tokens=assessment["estimated_tokens"],
                    actual_tokens=pip_token_guard.estimate_tokens(msg + response, assessment["max_output_tokens"]),
                )
                self.send_json({"response": response, "token_governor": assessment})
            elif parsed.path == "/revert-avatar":
                from pathlib import Path
                for ext in ["png", "jpg", "jpeg", "gif"]:
                    Path(f"avatar.{ext}").unlink(missing_ok=True)
                self.send_json({"status": "success"})
            elif parsed.path == "/upload-avatar":
                import base64
                from pathlib import Path
                import io
                length = int(self.headers.get("Content-Length", "0"))
                if length > 5 * 1024 * 1024:
                    self.send_json({"error": "avatar upload too large"}, status=413)
                    return
                body = self.rfile.read(length).decode("utf-8") if length else "{}"
                data = json.loads(body)
                b64_img = data.get("image", "")
                filename = data.get("filename", "avatar.png")
                
                raw_bytes = base64.b64decode(b64_img)
                
                # Apply vectorization/background removal if rembg is available
                try:
                    from rembg import remove
                    from PIL import Image
                    img = Image.open(io.BytesIO(raw_bytes))
                    out_img = remove(img)
                    out_io = io.BytesIO()
                    out_img.save(out_io, format="PNG")
                    raw_bytes = out_io.getvalue()
                    ext = "png"
                except ImportError:
                    print("rembg not available, saving original image")
                    ext = filename.split(".")[-1].lower()
                    if ext not in ["png", "jpg", "jpeg", "gif"]:
                        ext = "png"

                for old_ext in ["png", "jpg", "jpeg", "gif"]:
                    Path(f"avatar.{old_ext}").unlink(missing_ok=True)
                with open(f"avatar.{ext}", "wb") as f:
                    f.write(raw_bytes)
                self.send_json({"status": "success"})
            else:
                self.send_json({"error": "not found"}, status=404)
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=500)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Pip's local phone-friendly control panel.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--workspace", default="garden_spiders")
    parser.add_argument("--manifest", default="approved_workspaces.json")
    args = parser.parse_args()

    load_workspace(args.workspace, args.manifest)
    PipHandler.workspace_key = args.workspace
    PipHandler.manifest_path = args.manifest
    server = QuietThreadingHTTPServer((args.host, args.port), PipHandler)
    ip = local_ip()
    print("Pip control panel running.")
    print(f"Laptop URL: http://127.0.0.1:{args.port}")
    print(f"Phone URL on same Wi-Fi: http://{ip}:{args.port}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
