import re

def fix():
    with open('pip_control_panel.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # find the fairy_page() function
    parts = content.split('def fairy_page() -> str:\n')
    if len(parts) != 2:
        print("Couldn't find fairy_page()")
        return

    before = parts[0] + 'def fairy_page() -> str:\n'
    fairy_func = parts[1]
    
    # find the return f""" or return f'''
    fairy_func = fairy_func.replace('return f"""<!doctype html>', 'html_str = """<!doctype html>')
    
    # replace all {{ with { and }} with } in the HTML
    fairy_func = fairy_func.replace('{{', '{').replace('}}', '}')
    
    # put the sprite_html replacement back
    fairy_func = fairy_func.replace('{sprite_html}', '__SPRITE_HTML__')
    
    # we need to append the return statement
    # The end of the HTML is </html>"""
    fairy_func = fairy_func.replace('</html>"""', '</html>"""\n    return html_str.replace("__SPRITE_HTML__", sprite_html)')

    new_content = before + fairy_func

    with open('pip_control_panel.py', 'w', encoding='utf-8') as f:
        f.write(new_content)

    print("Fixed!")

if __name__ == '__main__':
    fix()
