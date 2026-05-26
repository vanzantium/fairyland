import re

def run():
    with open('pip_control_panel.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Update page() CSS
    content = content.replace('''    :root {
      --ink: #182018;
      --moss: #5c6f43;
      --leaf: #d9e2be;
      --silk: #f8f3df;
      --clay: #b96f4d;
      --shadow: rgba(28, 36, 23, 0.16);
    }''', '''    :root {
      --ink: #e0e6ff;
      --moss: #8b5cf6;
      --leaf: #10b981;
      --silk: #0f172a;
      --clay: #f59e0b;
      --shadow: rgba(139, 92, 246, 0.4);
    }''')
    
    content = content.replace('''      background:
        radial-gradient(circle at top left, rgba(217, 226, 190, .9), transparent 32rem),
        linear-gradient(140deg, #f8f3df 0%, #dfe8c7 54%, #c7d3a7 100%);''', '''      background:
        radial-gradient(circle at top left, rgba(16, 185, 129, 0.4), transparent 32rem),
        linear-gradient(140deg, #0f172a 0%, #1e1b4b 54%, #064e3b 100%);''')
        
    content = content.replace('''    .hero, .card {
      background: rgba(255, 253, 240, .82);
      border: 1px solid rgba(92, 111, 67, .22);''', '''    .hero, .card {
      background: rgba(30, 41, 59, 0.7);
      border: 1px solid rgba(16, 185, 129, 0.4);''')

    # 2. Update fairy_page() CSS
    content = content.replace('''    :root{
      --moss:#5c6f43;--leaf:#d9e2be;--silk:#f8f3df;
      --clay:#b96f4d;--ink:#182018;--quiet:#7d8663;
    }''', '''    :root{
      --moss:#8b5cf6;--leaf:#10b981;--silk:#0f172a;
      --clay:#f59e0b;--ink:#e0e6ff;--quiet:#94a3b8;
    }''')

    content = content.replace('''      background:
        radial-gradient(circle at 30% 20%,rgba(217,226,190,.8),transparent 60%),
        linear-gradient(160deg,#f0ede0 0%,#dce5c2 60%,#c8d5a8 100%);''', '''      background:
        radial-gradient(circle at 30% 20%,rgba(16,185,129,.5),transparent 60%),
        linear-gradient(160deg,#0f172a 0%,#1e1b4b 60%,#064e3b 100%);''')

    content = content.replace('''    .bubble{
      width:252px;
      background:rgba(251,248,234,.97);
      border:1.5px solid rgba(92,111,67,.28);
      border-radius:22px;
      padding:14px 15px 12px;
      box-shadow:0 6px 28px rgba(28,36,23,.14);''', '''    .bubble{
      width:252px;
      background:rgba(30,41,59,.92);
      border:1.5px solid rgba(16,185,129,.4);
      border-radius:22px;
      padding:14px 15px 12px;
      box-shadow:0 6px 28px rgba(139,92,246,.4);''')

    content = content.replace('''    .bubble::after{
      content:"";display:block;
      width:0;height:0;margin:8px auto 0;
      border:10px solid transparent;
      border-top-color:rgba(251,248,234,.97);
    }''', '''    .bubble::after{
      content:"";display:block;
      width:0;height:0;margin:8px auto 0;
      border:10px solid transparent;
      border-top-color:rgba(30,41,59,.92);
    }''')

    content = content.replace('''    .prop{font-size:.88rem;color:var(--ink);line-height:1.44;margin-bottom:7px;font-weight:700;}
    .evid{font-size:.76rem;color:#4d5b3b;line-height:1.32;margin-bottom:11px;}''', '''    .prop{font-size:.88rem;color:var(--ink);line-height:1.44;margin-bottom:7px;font-weight:700;}
    .evid{font-size:.76rem;color:#94a3b8;line-height:1.32;margin-bottom:11px;}''')

    content = content.replace('''    .d{
      width:6px;height:6px;border-radius:50%;
      background:#8a9e64;animation:bounce 1.5s ease-in-out infinite;opacity:.4;
    }''', '''    .d{
      width:6px;height:6px;border-radius:50%;
      background:var(--leaf);animation:bounce 1.5s ease-in-out infinite;opacity:.8;
    }''')

    # Remove the massive SVG block
    match = re.search(r'    sprite_html = """<svg class="sprite".*?</svg>"""', content, re.DOTALL)
    if match:
        content = content.replace(match.group(0), '    sprite_html = """<img class="sprite" id="fairy" src="/default-fairy" width="112" height="179" style="object-fit: contain; filter: drop-shadow(0 5px 14px rgba(16,185,129,0.5));" onclick="tap()">"""')
    
    # 3. Add /default-fairy to do_GET
    get_fairy = '''            elif parsed.path == "/avatar":'''
    new_get_fairy = '''            elif parsed.path == "/default-fairy":
                try:
                    with open("default_fairy.png", "rb") as f:
                        self.send_header("Content-Type", "image/png")
                        self.send_header("Content-Length", str(Path("default_fairy.png").stat().st_size))
                        self.end_headers()
                        self.wfile.write(f.read())
                except Exception:
                    self.send_json({"error": "not found"}, status=404)
            elif parsed.path == "/avatar":'''
    content = content.replace(get_fairy, new_get_fairy)

    # 4. Add Revert Avatar button to HTML
    revert_html = '''<label for="avatar_file" style="cursor:pointer;color:var(--quiet);">change avatar</label>
  <input type="file" id="avatar_file" style="display:none;" accept="image/png, image/jpeg, image/jpg" onchange="uploadAvatar()">'''
    new_revert_html = '''<label for="avatar_file" style="cursor:pointer;color:var(--quiet);margin-right:8px;">change avatar</label>
  <input type="file" id="avatar_file" style="display:none;" accept="image/png, image/jpeg, image/jpg" onchange="uploadAvatar()">
  <span style="cursor:pointer;color:var(--clay);" onclick="revertAvatar()">revert original</span>'''
    content = content.replace(revert_html, new_revert_html)
    
    # 5. Add revertAvatar JS
    revert_js = '''  async function poll() {'''
    new_revert_js = '''  async function revertAvatar() {
    await fetch('/revert-avatar', {method: 'POST'});
    location.reload();
  }

  async function poll() {'''
    content = content.replace(revert_js, new_revert_js)

    # 6. Add /revert-avatar to do_POST
    post_revert = '''            elif parsed.path == "/upload-avatar":'''
    new_post_revert = '''            elif parsed.path == "/revert-avatar":
                from pathlib import Path
                for ext in ["png", "jpg", "jpeg", "gif"]:
                    Path(f"avatar.{ext}").unlink(missing_ok=True)
                self.send_json({"status": "success"})
                self.redirect_home()
            elif parsed.path == "/upload-avatar":'''
    content = content.replace(post_revert, new_post_revert)

    with open('pip_control_panel.py', 'w', encoding='utf-8') as f:
        f.write(content)

    print("Aesthetic updated successfully.")

if __name__ == '__main__':
    run()
