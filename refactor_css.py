import os
import re
import hashlib

template_dir = r"C:\Users\Administrator\Desktop\TH\services\dashboard\templates"
static_dir = r"C:\Users\Administrator\Desktop\TH\services\dashboard\static"
css_file = os.path.join(static_dir, "style.css")

os.makedirs(static_dir, exist_ok=True)

class_map = {}
css_content = ""

for filename in os.listdir(template_dir):
    if not filename.endswith(".html"):
        continue
    filepath = os.path.join(template_dir, filename)
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    def style_replacer(m):
        style_string = m.group(1).strip()
        if "{{" in style_string or "{%" in style_string:
            return m.group(0)
        
        if not style_string.endswith(";"):
            style_string += ";"

        style_hash = hashlib.md5(style_string.encode()).hexdigest()[:6]
        class_name = f"util-{style_hash}"
        
        if class_name not in class_map:
            class_map[class_name] = style_string
            global css_content
            css_content += f".{class_name} {{ {style_string} }}\n"
            
        return f'class="{class_name}"'

    # 1. Replace style="..." with class="..."
    new_content = re.sub(r'style="([^"]*)"', style_replacer, content)

    # 2. Merge multiple class="..." in the same tag
    def tag_replacer(m):
        tag_inner = m.group(1)
        classes = []
        def class_extractor(cm):
            classes.extend(cm.group(1).split())
            return ""
        
        cleaned_inner = re.sub(r'class="([^"]*)"', class_extractor, tag_inner)
        
        if classes:
            uniq_classes = []
            for c in classes:
                if c not in uniq_classes:
                    uniq_classes.append(c)
            # Make sure there is space before class string if cleaned_inner doesn't end with space
            # Actually, `cleaned_inner` is just the tag name and other attributes.
            return f"<{cleaned_inner.rstrip()} class=\"{' '.join(uniq_classes)}\">"
        return m.group(0)

    # Match `<tag ...>`
    new_content2 = re.sub(r'<([a-zA-Z0-9\-]+(?:(?:\s+[^>"]*)|(?:\s+[a-zA-Z\-]+="[^"]*"))*)>', tag_replacer, new_content)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content2)

with open(css_file, "w", encoding="utf-8") as f:
    f.write(css_content)

print(f"Extracted {len(class_map)} static CSS styles to services/dashboard/static/style.css")
