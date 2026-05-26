#!/usr/bin/env python3
"""
pip_hound.py — The Receipt Clerk
Indexes .txt/.md files from the brain folder using SQLite FTS5 for lightning-fast,
hallucination-free snippet search.
"""

import os
import sqlite3
from pathlib import Path
from datetime import datetime

# Paths are anchored to the pip-v0 directory and the parent brain folder
import pip_config

def get_vault_path() -> Path:
    return pip_config.get_memory_path()

def get_db_path() -> Path:
    return pip_config.get_memory_path() / "text_hound.sqlite"

def build_index(root: str = None, db_path: str = None):
    root = root or str(get_vault_path())
    db_path = db_path or str(get_db_path())
    """Walk root, index files with FTS5."""
    print(f"[Hound] Building index for {root}...")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE IF NOT EXISTS files(id INTEGER PRIMARY KEY, path TEXT UNIQUE)")
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS idx USING fts5(path, heading, body, tokenize='porter unicode61')"
    )
    conn.execute("DELETE FROM idx")  # simple full rebuild
    conn.execute("DELETE FROM files")
    conn.commit()

    texts = []
    # Explicitly avoid indexing massive directories or pip's own internal databases
    ignore_dirs = {".git", ".claude", "node_modules", "pip-v0"}
    
    for dirpath, dirnames, filenames in os.walk(root):
        # Mutate dirnames in-place to skip ignored folders
        dirnames[:] = [d for d in dirnames if d not in ignore_dirs]
        
        for fname in filenames:
            if not fname.lower().endswith((".txt", ".md")):
                continue
            full = os.path.join(dirpath, fname)
            try:
                with open(full, "r", encoding="utf-8", errors="replace") as f:
                    raw = f.read()
            except Exception:
                continue

            heading = fname
            body = raw
            texts.append((full, heading, body))

    cur = conn.cursor()
    cur.executemany("INSERT OR IGNORE INTO files(path) VALUES(?)", [(p,) for p, _, _ in texts])
    for path, heading, body in texts:
        cur.execute("INSERT INTO idx(path, heading, body) VALUES(?,?,?)", (path, heading, body))
    conn.commit()
    conn.close()
    print(f"[Hound] Indexed {len(texts)} files.")
    return len(texts)

def check_index(db_path: str = None) -> bool:
    db_path = db_path or str(get_db_path())
    """Check if the index exists and has data."""
    if not os.path.exists(db_path):
        return False
    try:
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT count(*) FROM files").fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        return False

def search(query: str, limit: int = 8, db_path: str = None):
    db_path = db_path or str(get_db_path())
    """Return list of {path, heading, snippet}."""
    if not check_index(db_path):
        build_index()
        
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        # simple FTS5 snippet, ~64 chars around match
        sql = """
            SELECT path, heading, snippet(idx, 1, '<mark>', '</mark>', '...', 32) AS snippet
            FROM idx
            WHERE idx MATCH ?
            LIMIT ?
        """
        rows = conn.execute(sql, (query, limit)).fetchall()
        conn.close()
        # Convert Row objects to dicts so they are JSON serializable
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"[Hound] Search error: {e}")
        return []

def capsule(query: str, output_dir: str = None, db_path: str = None):
    output_dir = output_dir or str(get_vault_path() / "capsules")
    db_path = db_path or str(get_db_path())
    """Create a capsule.md from selected search results."""
    rows = search(query, limit=20, db_path=db_path)
    if not rows:
        return None

    # Collect unique source files
    files = list({r["path"] for r in rows})
    excerpts = []
    for r in rows:
        # FTS5 snippets can sometimes have weird linebreaks, strip them for the bullet list
        clean_snippet = r['snippet'].replace('\n', ' ').strip()
        excerpts.append(f"- **{r['heading']}**: {clean_snippet}")

    capsule_text = f"""---
capsule_type: "search_compression"
query: "{query}"
created: "{datetime.utcnow().isoformat()}"
source_files:
{chr(10).join(f'- {f}' for f in files)}
thread: "manual"
status: "draft"
---

# Core signal
(Your note here)

# Repeating terms
(Extract from results)

# What changed
...

# Open loop
...

# Next action
...

## Raw excerpts
{chr(10).join(excerpts)}
"""
    os.makedirs(output_dir, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    fname = f"capsule_{stamp}.md"
    full = os.path.join(output_dir, fname)
    with open(full, "w", encoding="utf-8") as f:
        f.write(capsule_text)
    return full

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python pip_hound.py build | search <query> | capsule <query>")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "build":
        build_index()
    elif cmd == "search":
        q = " ".join(sys.argv[2:])
        results = search(q)
        for r in results:
            print(f"\n📄 {r['heading']}")
            print(r["snippet"])
    elif cmd == "capsule":
        q = " ".join(sys.argv[2:])
        out = capsule(q)
        if out:
            print(f"Capsule written → {out}")
        else:
            print("No results found.")
