import json
import os
from jinja2 import Environment, FileSystemLoader
from shared.types.research import ResearchRunResult

REPORT_DIR = "artifacts/research"

def _ensure_dir():
    if not os.path.exists(REPORT_DIR):
        os.makedirs(REPORT_DIR)

def save_json(result: ResearchRunResult) -> str:
    _ensure_dir()
    filepath = os.path.join(REPORT_DIR, f"{result.run_id}.json")
    with open(filepath, "w") as f:
        # Pydantic v2 compatible
        f.write(result.model_dump_json(indent=2))
    return filepath

def generate_html_report(result: ResearchRunResult) -> str:
    _ensure_dir()
    filepath = os.path.join(REPORT_DIR, f"{result.run_id}.html")
    
    # Render using the existing dashboard templates 
    env = Environment(loader=FileSystemLoader("services/dashboard/templates"))
    try:
        template = env.get_template("research_report_template.html")
        html_content = template.render(
            run=result,
            variants=result.variants
        )
    except Exception as e:
        # Fallback raw HTML if template missing
        html_content = f"<html><body><h1>Research Run: {result.run_id}</h1><p>Template error: {e}</p></body></html>"

    with open(filepath, "w") as f:
        f.write(html_content)
        
    return filepath
