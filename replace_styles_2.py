import os
import re

target_dir = r"C:\Users\Administrator\Desktop\TH\services\dashboard\templates"

replacements = {
    r'style="text-align: right; font-size: 0\.6rem;"': 'class="text-right text-xxs"',
    r'style="font-size: 0\.6rem; color: var\(--text-muted\); text-transform: uppercase; letter-spacing: 1px; margin-top: 0\.5rem;"': 'class="text-xxs text-muted text-upper letter-spacing-1 mt-2"',
    r'style="background: rgba\(0,0,0,0\.2\);"': 'class="bg-dark-overlay"',
    r'style="display: flex; gap: 1rem; align-items: center;"': 'class="flex gap-4 align-center"',
    r'style="padding: 1rem; display: flex; justify-content: space-between; align-items: center;"': 'class="p-3 flex justify-between align-center"',
    r'style="padding: 5rem; text-align: center;"': 'class="p-5 text-center"',
    r'style="opacity: 0\.6;"': 'class="opacity-60"',
    r'style="border: 1px solid var\(--accent-cyan\); color: var\(--accent-cyan\); background: transparent;"': 'class="border-theme text-cyan bg-transparent"',
    r'style="margin-bottom: 1\.5rem;"': 'class="mb-4"',
    r'style="font-size: 0\.6rem; color: var\(--text-muted\); font-family: monospace;"': 'class="text-xxs text-muted text-mono"',
    r'style="background: rgba\(0,0,0,0\.2\); border: 1px solid rgba\(255,255,255,0\.05\); border-radius: 4px; padding: 1rem;"': 'class="bg-dark-overlay border-divider p-3"',
    r'style="width: 250px;"': 'class="w-250"',
    r'style="padding: 4rem; text-align: center;"': 'class="hud-empty-state"',
    r'style="color: var\(--text-main\); font-weight: 700;"': 'class="text-main text-bold"',
    r'style="font-size: 0\.7rem; color: var\(--text-main\); line-height: 1\.5;"': 'class="text-xs text-main line-height-relaxed"',
    r'style="font-size: 0\.55rem; color: var\(--text-muted\); letter-spacing: 1px; text-transform: uppercase; display: block; margin-bottom: 0\.4rem;"': 'class="text-mini text-muted letter-spacing-1 text-upper display-block mb-1"',
    r'style="text-align: right; font-family: monospace; font-weight: 900; font-size: 0\.85rem;"': 'class="text-right text-mono text-black text-sm"',
    r'style="text-align: right; font-family: monospace; font-weight: 900; font-size: 0\.85rem; color: var\(--accent-pink\);"': 'class="text-right text-mono text-black text-sm text-pink"',
    r'style="text-align: center; font-family: monospace; font-weight: 900;"': 'class="text-center text-mono text-black"',
    r'style="font-size: 0\.65rem; color: var\(--text-muted\);"': 'class="text-xxs text-muted"',
    
    # Catch all single styles
    r'style="color: var\(--accent-yellow\);"': 'class="text-yellow"',
    r'style="color: var\(--accent-purple\);"': 'class="text-purple"',
    r'style="width: 100%;"': 'class="w-full"',
    r'style="margin-top: 1rem;"': 'class="mt-3"',
    r'style="margin-bottom: 1rem;"': 'class="mb-3"',
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
