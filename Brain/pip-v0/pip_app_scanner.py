#!/usr/bin/env python3
import json
import subprocess
from pathlib import Path

import pip_platform
import pip_app_skills


def _app_entry(name: str, publisher: str = "", enabled: bool = False) -> dict:
    return {"name": name, "publisher": publisher, "enabled": enabled, "level": 1, "xp": 0}


def _windows_apps() -> list[dict]:
    script = """
    $apps = Get-ItemProperty HKLM:\\Software\\Wow6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* | 
        Select-Object DisplayName, Publisher | 
        Where-Object { $_.DisplayName -ne $null }
    $apps += Get-ItemProperty HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* | 
        Select-Object DisplayName, Publisher | 
        Where-Object { $_.DisplayName -ne $null }
    $apps += Get-ItemProperty HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* | 
        Select-Object DisplayName, Publisher | 
        Where-Object { $_.DisplayName -ne $null }
    
    $uniqueApps = $apps | Sort-Object DisplayName -Unique
    $uniqueApps | ConvertTo-Json -Compress
    """
    try:
        output = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", script],
            text=True,
            **pip_platform.hidden_subprocess_kwargs(),
        )
        if output.strip():
            raw = json.loads(output)
            if isinstance(raw, dict):
                raw = [raw]
            apps = [{"name": item.get("DisplayName", ""), "publisher": item.get("Publisher", "")} for item in raw]
            
            filtered = []
            skip_keywords = ["Update", "Redistributable", "Runtime", "SDK", "Driver", "Module", "Service", "Framework", "Library"]
            for a in apps:
                n = a["name"]
                if not n or any(k in n for k in skip_keywords):
                    continue
                if "Microsoft" in str(a.get("publisher", "")) and "Windows" in n:
                    continue
                filtered.append(_app_entry(n, a.get("publisher", "")))
            
            filtered.sort(key=lambda x: x["name"])
            return filtered
    except Exception as e:
        print(f"App scanner error: {e}")
    return []


def _macos_apps() -> list[dict]:
    candidates: list[dict] = []
    for base in [Path("/Applications"), Path.home() / "Applications"]:
        if not base.exists():
            continue
        for app in base.glob("*.app"):
            candidates.append(_app_entry(app.stem, "macOS application bundle"))
    candidates.sort(key=lambda item: item["name"].lower())
    return candidates


def _linux_apps() -> list[dict]:
    candidates: list[dict] = []
    seen: set[str] = set()
    app_dirs = [
        Path("/usr/share/applications"),
        Path("/usr/local/share/applications"),
        Path.home() / ".local" / "share" / "applications",
    ]
    for app_dir in app_dirs:
        if not app_dir.exists():
            continue
        for desktop in app_dir.glob("*.desktop"):
            try:
                lines = desktop.read_text(encoding="utf-8", errors="ignore").splitlines()
            except Exception:
                continue
            name = ""
            hidden = False
            for line in lines:
                if line.startswith("NoDisplay=true") or line.startswith("Hidden=true"):
                    hidden = True
                elif line.startswith("Name=") and not name:
                    name = line.split("=", 1)[1].strip()
            if hidden or not name or name in seen:
                continue
            seen.add(name)
            candidates.append(_app_entry(name, "desktop entry"))
    candidates.sort(key=lambda item: item["name"].lower())
    return candidates


def get_installed_apps() -> list[dict]:
    if pip_platform.is_windows():
        return _windows_apps()
    if pip_platform.is_macos():
        return _macos_apps()
    if pip_platform.is_linux():
        return _linux_apps()
    return []


def scan_and_save():
    apps = get_installed_apps()
    import pip_config
    mem_dir = pip_config.get_memory_path()
    
    out_file = mem_dir / "apps.json"
    
    existing = []
    if out_file.exists():
        try:
            with open(out_file, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            pass
            
    existing_map = {e["name"]: e for e in existing}
    
    for a in apps:
        if a["name"] not in existing_map:
            existing_map[a["name"]] = a
            
    final_list = list(existing_map.values())
    
    # Force inject known developer shells that might not appear in OS app registries.
    for shell_entry in pip_app_skills.developer_shell_app_entries():
        if not any(a["name"] == shell_entry["name"] for a in final_list):
            final_list.append(shell_entry)
    if not any(a["name"] == "Cursor" for a in final_list):
        final_list.append({"name": "Cursor", "enabled": True, "level": 1, "xp": 0})
            
    final_list.sort(key=lambda x: x["name"])
    
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(final_list, f, indent=2)
        
    return final_list

if __name__ == "__main__":
    res = scan_and_save()
    print(f"Scanned {len(res)} apps.")
