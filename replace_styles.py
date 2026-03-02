import os
import re

target_dir = r"C:\Users\Administrator\Desktop\TH\services\dashboard\templates"

replacements = {
    # Badges
    r'style="background: rgba\(155, 81, 224, 0\.1\); color: var\(--accent-purple\); border: 1px solid var\(--accent-purple\);"': 'class="badge-purple"',
    r'style="background: rgba\(86, 204, 242, 0\.1\); color: var\(--accent-cyan\); border: 1px solid var\(--accent-cyan\);"': 'class="badge-cyan"',
    r'style="background: rgba\(86, 204, 242, 0\.1\); color: var\(--accent-cyan\); border: 1px solid var\(--accent-cyan\); font-size: 0\.6rem;"': 'class="badge-cyan text-xxs"',
    r'style="background: rgba\(86, 204, 242, 0\.05\); color: var\(--accent-cyan\); border: 1px solid rgba\(86, 204, 242, 0\.2\); font-size: 0\.55rem;"': 'class="badge-cyan-dim badge-sm"',
    r'style="background: rgba\(235, 47, 150, 0\.1\); color: var\(--accent-pink\); border: 1px solid var\(--accent-pink\);"': 'class="badge-pink"',
    r'style="background: rgba\(242, 201, 76, 0\.1\); color: var\(--accent-yellow\); border: 1px solid var\(--accent-yellow\);"': 'class="badge-yellow"',
    r'style="background: rgba\(39, 174, 96, 0\.1\); color: var\(--accent-green\); border: 1px solid var\(--accent-green\);"': 'class="badge-green"',
    
    # Conditional badges
    r'''style="background: \{\% if item\.severity == 'CRITICAL' \%\}rgba\(235, 47, 150, 0\.1\)\{\% elif item\.severity == 'WARNING' \%\}rgba\(242, 201, 76, 0\.1\)\{\% else \%\}rgba\(86, 204, 242, 0\.1\)\{\% endif \%\}; color: \{\% if item\.severity == 'CRITICAL' \%\}var\(--accent-pink\)\{\% elif item\.severity == 'WARNING' \%\}var\(--accent-yellow\)\{\% else \%\}var\(--accent-cyan\)\{\% endif \%\}; border: 1px solid \{\% if item\.severity == 'CRITICAL' \%\}var\(--accent-pink\)\{\% elif item\.severity == 'WARNING' \%\}var\(--accent-yellow\)\{\% else \%\}var\(--accent-cyan\)\{\% endif \%\}; font-size: 0\.55rem; font-weight: 900;"''': 
    '''class="badge-sm {% if item.severity == 'CRITICAL' %}badge-pink{% elif item.severity == 'WARNING' %}badge-yellow{% else %}badge-cyan{% endif %}"''',

    r'''style="background: \{\% if item\.status == 'OPEN' \%\}rgba\(242, 201, 76, 0\.1\)\{\% else \%\}rgba\(39, 174, 96, 0\.1\)\{\% endif \%\}; color: \{\% if item\.status == 'OPEN' \%\}var\(--accent-yellow\)\{\% else \%\}var\(--accent-green\)\{\% endif \%\}; border: 1px solid \{\% if item\.status == 'OPEN' \%\}var\(--accent-yellow\)\{\% else \%\}var\(--accent-green\)\{\% endif \%\}; font-size: 0\.55rem; font-weight: 900;"''':
    '''class="badge-sm {% if item.status == 'OPEN' %}badge-yellow{% else %}badge-green{% endif %}"''',

    # Alignments
    r'style="text-align: center;"': 'class="text-center"',
    r'style="text-align: right;"': 'class="text-right"',
    
    # Widths
    r'style="width: 150px;"': 'class="w-150"',
    r'style="width: 120px;"': 'class="w-120"',
    r'style="width: 100px;"': 'class="w-100"',
    r'style="height: 350px;"': 'class="h-350"',
    r'style="text-align: right; width: 120px;"': 'class="text-right w-120"',
    r'style="text-align: right; width: 150px;"': 'class="text-right w-150"',
    r'style="text-align: center; width: 100px;"': 'class="text-center w-100"',
    r'style="text-align: right; width: 100px;"': 'class="text-right w-100"',
    
    # Typography
    r'style="font-family: monospace; font-size: 0\.7rem; color: var\(--text-muted\);"': 'class="text-mono text-xs text-muted"',
    r'style="font-family: monospace; font-size: 0\.65rem; color: var\(--text-muted\);"': 'class="text-mono text-xxs text-muted"',
    r'style="text-align: right; font-family: monospace; font-size: 0\.65rem; color: var\(--text-muted\);"': 'class="text-mono text-xxs text-muted text-right"',
    r'style="text-align: right; font-family: monospace; font-size: 0\.75rem;"': 'class="text-mono text-xs text-right"',
    r'style="font-weight: 800; color: var\(--text-main\); margin-bottom: 0\.25rem;"': 'class="text-bold text-main mb-1"',
    r'style="font-weight: 800; color: var\(--text-main\);"': 'class="text-bold text-main"',
    r'style="font-weight: 900; color: var\(--text-main\);"': 'class="text-black text-main"',
    r'style="font-weight: 800; color: var\(--accent-cyan\);"': 'class="text-bold text-cyan"',
    r'style="font-size: 0\.65rem; color: var\(--text-muted\); line-height: 1\.4;"': 'class="text-xxs text-muted line-height-relaxed"',
    r'style="font-size: 0\.7rem; color: var\(--text-muted\); line-height: 1\.4;"': 'class="text-xs text-muted line-height-relaxed"',
    r'style="font-size: 0\.6rem;"': 'class="text-xxs"',
    r'style="font-size: 0\.55rem;"': 'class="text-mini"',
    r'style="font-size: 0\.6rem; text-align: right;"': 'class="text-xxs text-right"',
    r'style="font-size: 0\.6rem; color: var\(--text-muted\);"': 'class="text-xxs text-muted"',
    r'style="font-size: 0\.5rem; color: var\(--text-muted\);"': 'class="text-micro text-muted"',
    r'style="font-size: 0\.55rem; color: var\(--text-muted\); text-transform: uppercase; letter-spacing: 1px; margin-top: 0\.5rem;"': 'class="text-mini text-muted text-upper letter-spacing-1 mt-2"',
    r'style="font-size: 0\.55rem; color: var\(--text-muted\); letter-spacing: 1px; text-transform: uppercase; margin-bottom: 0\.4rem;"': 'class="text-mini text-muted text-upper letter-spacing-1 mb-2"',
    r'style="color: var\(--text-muted\); opacity: 0\.5;"': 'class="text-muted opacity-50"',
    r'style="color: var\(--text-muted\);"': 'class="text-muted"',
    r'style="color: var\(--text-main\);"': 'class="text-main"',
    r'style="color: var\(--accent-green\);"': 'class="text-green"',
    r'style="color: var\(--accent-pink\);"': 'class="text-pink"',
    
    # Layouts & spacing
    r'style="padding: 1rem;"': 'class="p-3"',
    r'style="padding: 1\.25rem;"': 'class="p-4"',
    r'style="padding: 1\.5rem;"': 'class="p-5"',
    r'style="margin-bottom: 2rem;"': 'class="mb-4"',
    r'style="display: flex; gap: 0\.5rem;"': 'class="flex gap-3"',
    r'style="display: flex; gap: 0\.5rem; align-items: center;"': 'class="flex gap-3 align-center"',
    r'style="display: flex; align-items: center; gap: 0\.4rem;"': 'class="flex align-center gap-2"',
    r'style="display: flex; align-items: center; gap: 1\.5rem;"': 'class="flex align-center gap-5"',
    
    # Complex Components
    r'style="padding: 4rem; text-align: center; color: var\(--accent-green\); font-weight: 800; letter-spacing: 2px;"': 'class="hud-empty-state-green"',
    r'style="padding: 4rem; text-align: center; color: var\(--text-muted\); font-weight: 800; letter-spacing: 2px;"': 'class="hud-empty-state"',
    r'style="padding: 6rem; text-align: center;"': 'class="hud-empty-state p-5"',
    r'style="padding: 1rem; color: var\(--text-muted\); font-size: 0\.8rem; letter-spacing: 1px;"': 'class="hud-panel-desc"',
    
    r'style="padding: 1rem; color: var\(--text-muted\); font-size: 0\.75rem; letter-spacing: 1px; border-bottom: 1px solid rgba\(255,255,255,0\.05\);"': 'class="hud-panel-desc text-xs border-divider"',
    r'style="font-size: 1rem; color: var\(--accent-pink\); font-weight: 900; margin-bottom: 1rem; letter-spacing: 2px;"': 'class="text-sm text-pink text-black mb-3 letter-spacing-2"'
}

def advanced_replace(content):
    # First apply exact regex text replacements
    for pattern, repl in replacements.items():
        content = re.sub(pattern, repl, content)
        
    # Merge classes: class="badge" class="badge-cyan" -> class="badge badge-cyan"
    while re.search(r'class="([^"]+)"\s+class="([^"]+)"', content):
        content = re.sub(r'class="([^"]+)"\s+class="([^"]+)"', 
                         lambda m: f'class="{m.group(1)} {m.group(2)}"', 
                         content)
                         
    # Deduplicate classes just in case
    def dedup_classes(match):
        cls_attr = match.group(1)
        classes = cls_attr.split()
        seen = set()
        out = []
        for c in classes:
            if c not in seen:
                out.append(c)
                seen.add(c)
        return 'class="' + ' '.join(out) + '"'

    content = re.sub(r'class="([^"]+)"', dedup_classes, content)

    return content

count_files_modified = 0

for root, _, files in os.walk(target_dir):
    for filename in files:
        if filename.endswith(".html"):
            path = os.path.join(root, filename)
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            new_content = advanced_replace(content)
            
            if new_content != content:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                count_files_modified += 1

print(f"Modified {count_files_modified} files.")
