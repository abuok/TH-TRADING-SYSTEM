import os
import re

target_dir = r"C:\Users\Administrator\Desktop\TH\services\dashboard\templates"

rule_to_class = {
    "font-family: monospace": "text-mono",
    "font-weight: 800": "text-bold",
    "font-weight: 700": "text-bold",
    "font-weight: 900": "text-black",
    "text-transform: uppercase": "text-upper",
    "line-height: 1.4": "line-height-relaxed",
    "line-height: 1.5": "line-height-relaxed",
    "line-height: 1.3": "line-height-relaxed",
    "text-align: center": "text-center",
    "text-align: right": "text-right",
    "text-align: left": "text-left",
    "display: flex": "flex",
    "display: grid": "grid",
    "display: block": "display-block",
    "justify-content: space-between": "justify-between",
    "align-items: center": "align-center",
    "align-items: flex-start": "align-start",
    "flex-wrap: wrap": "flex-wrap",
    "overflow: hidden": "overflow-hidden",
    "overflow-x: auto": "overflow-x-auto",
    "font-style: italic": "font-italic",
    "text-decoration: none": "no-underline",
    "flex: 1": "flex-1",
    "color: var(--text-muted)": "text-muted",
    "color: var(--text-main)": "text-main",
    "color: var(--accent-cyan)": "text-cyan",
    "color: var(--accent-pink)": "text-pink",
    "color: var(--accent-yellow)": "text-yellow",
    "color: var(--accent-green)": "text-green",
    "color: var(--accent-purple)": "text-purple",
    "color: #000": "text-black text-black-color",
    "font-size: 1.5rem": "text-xl",
    "font-size: 1.1rem": "text-lg",
    "font-size: 1rem": "text-md",
    "font-size: 0.9rem": "text-sm",
    "font-size: 0.85rem": "text-sm",
    "font-size: 0.8rem": "text-sm",
    "font-size: 0.75rem": "text-xs",
    "font-size: 0.7rem": "text-xs",
    "font-size: 0.65rem": "text-xxs",
    "font-size: 0.6rem": "text-xxs",
    "font-size: 0.55rem": "text-mini",
    "font-size: 0.5rem": "text-micro",
    "letter-spacing: 1px": "letter-spacing-1",
    "letter-spacing: 2px": "letter-spacing-2",
    "letter-spacing: 0.5px": "",
    "gap: 1.5rem": "gap-5",
    "gap: 1rem": "gap-4",
    "gap: 0.75rem": "gap-3",
    "gap: 0.5rem": "gap-2",
    "gap: 0.4rem": "gap-2",
    "background: rgba(0,0,0,0.2)": "bg-dark-overlay",
    "background: rgba(0,0,0,0.3)": "bg-darker-overlay",
    "background: rgba(0,0,0,0.4)": "bg-darker-overlay",
    "background: transparent": "bg-transparent",
    "background: var(--accent-green)": "bg-green",
    "background: rgba(155, 81, 224, 0.03)": "bg-purple-dim",
    "background: rgba(86, 204, 242, 0.05)": "bg-cyan-dim",
    "border-radius: 4px": "rounded",
    "border-radius: 3px": "rounded",
    "border: 1px solid rgba(255,255,255,0.05)": "border-theme",
    "border-bottom: 1px solid rgba(255,255,255,0.05)": "border-divider",
    "border-right: 1px solid rgba(255,255,255,0.05)": "border-right",
    "border-left: 4px solid var(--accent-purple)": "border-left-purple",
    "border: 1px solid var(--border-color)": "border-theme",  # assuming it's border-theme
    "border-color: var(--accent-green)": "border-green",
    "margin-bottom: 2rem": "mb-4",
    "margin-bottom: 1.5rem": "mb-3",
    "margin-bottom: 1rem": "mb-3",
    "margin-bottom: 0.5rem": "mb-2",
    "margin-bottom: 0.4rem": "mb-1",
    "margin-bottom: 0.25rem": "mb-1",
    "margin-bottom: 0.2rem": "mb-1",
    "margin-top: 2rem": "mt-4",
    "margin-top: 1rem": "mt-3",
    "margin-top: 0.8rem": "mt-2",
    "margin-top: 0.5rem": "mt-2",
    "margin-top: 0.2rem": "mt-1",
    "margin: 0": "m-0",
    "padding: 1rem": "p-3",
    "padding: 0.75rem": "p-2",
    "padding: 0.5rem": "p-2",
    "padding-bottom: 0.5rem": "pb-2",
    "padding: 0 0.5rem": "px-2",
    "padding-left: 1rem": "pl-3",
    "padding: 0.3rem 0.8rem": "px-2 py-1",
    "padding: 0.3rem 0.6rem": "px-2 py-1",
    "padding: 4rem": "p-6",
    "width: 150px": "w-150",
    "width: 120px": "w-120",
    "width: 100px": "w-100",
    "width: 250px": "w-250",
    "width: 100%": "w-full",
    "min-width: 120px": "w-120",
    "min-width: 180px": "w-180",
    "height: 350px": "h-350",
    "height: 450px": "h-450",
    "opacity: 0.6": "opacity-60",
    "opacity: 0.5": "opacity-50",
    "opacity: 0.4": "opacity-40",
    "opacity: 0.7": "opacity-70",
    "flex-direction: column": "flex-col",
    "background: rgba(242, 201, 76, 0.1)": "bg-yellow-dim",
    "border: 1px solid var(--accent-yellow)": "border-yellow",
    "background: rgba(235, 47, 150, 0.1)": "bg-pink-dim",
    "border: 1px solid var(--accent-pink)": "border-pink",
    "background: rgba(155, 81, 224, 0.1)": "bg-purple-dim-2",
    "border: 1px solid var(--accent-purple)": "border-purple",
    "background: rgba(255, 255, 255, 0.03)": "bg-glass-light",
    "border: 1px solid rgba(255, 255, 255, 0.1)": "border-glass",
    "padding: 1.25rem": "p-4",
    "font-size: 2rem": "text-2xl",
    "font-size: 2.5rem": "text-3xl",
    "font-size: 1.2rem": "text-lg",
    "font-size: 1.25rem": "text-lg",
    "line-height: 1": "line-height-1",
    "line-height: 1.2": "line-height-1-2",
    "gap: 2rem": "gap-6",
    "grid-template-columns: 1fr 1fr": "grid-cols-2",
    "height: 400px": "h-400",
    "margin-bottom: 0.75rem": "mb-3",
    "align-items: baseline": "align-baseline",
    "color: var(--accent-orange)": "text-orange",
    "max-width: 600px": "max-w-600",
    "margin: 0 auto": "mx-auto",
}


def handle_tag(tag_match):
    tag = tag_match.group(0)

    style_match = re.search(r'style="([^"]*)"', tag)
    if not style_match:
        return tag

    style_content = style_match.group(1)

    if "{%" in style_content or "{{" in style_content:
        return tag

    rules = [r.strip() for r in style_content.split(";") if r.strip()]
    new_classes = set()
    unmapped = []

    for rule in rules:
        normalized_rule = re.sub(r"\s+", " ", rule)
        normalized_rule = re.sub(r"\s*:\s*", ": ", normalized_rule)

        found = False
        for pattern_str, cls in rule_to_class.items():
            if normalized_rule == pattern_str:
                if cls:
                    for c in cls.split():
                        new_classes.add(c)
                found = True
                break

        if not found:
            unmapped.append(rule)

    if not new_classes:
        return tag

    # Remove old style
    tag = re.sub(r'\s*style="[^"]*"', "", tag)

    if unmapped:
        new_style = "; ".join(unmapped) + ";"
        # Put it just before the ending >
        # Handles self closing tags like <div /> and standard <div ... >
        if tag.endswith("/>"):
            tag = tag[:-2] + f' style="{new_style}"/>'
        else:
            tag = tag[:-1] + f' style="{new_style}">'

    class_match = re.search(r'class="([^"]*)"', tag)
    if class_match:
        existing_classes = set(class_match.group(1).split())
        all_classes = existing_classes.union(new_classes)
        new_class_attr = 'class="' + " ".join(all_classes) + '"'
        tag = re.sub(r'class="[^"]*"', new_class_attr, tag)
    else:
        if tag.endswith("/>"):
            tag = tag[:-2] + f' class="{" ".join(new_classes)}"/>'
        else:
            tag = tag[:-1] + f' class="{" ".join(new_classes)}">'

    return tag


count_files_modified = 0

for root, _, files in os.walk(target_dir):
    for filename in files:
        if filename.endswith(".html"):
            path = os.path.join(root, filename)
            with open(path, encoding="utf-8") as f:
                content = f.read()

            new_content = re.sub(
                r'<[a-zA-Z0-9\-]+(?:[^>"]|"[^"]*")*>', handle_tag, content
            )

            if new_content != content:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                count_files_modified += 1

print(f"Modified {count_files_modified} files.")
