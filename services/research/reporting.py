import json
import os
from datetime import datetime

from jinja2 import Environment, FileSystemLoader

from shared.types.research import ResearchRunResult
from shared.types.calibration import CalibrationReport

_ARTIFACT_DIR = os.path.join("artifacts", "research")
_TEMPLATE_DIR = os.path.join("services", "dashboard", "templates")


def save_research_run(run_result: ResearchRunResult) -> str:
    """Saves a ResearchRunResult to the artifact directory as JSON."""
    os.makedirs(_ARTIFACT_DIR, exist_ok=True)
    filepath = os.path.join(_ARTIFACT_DIR, f"{run_result.run_id}.json")
    with open(filepath, "w") as f:
        f.write(run_result.model_dump_json(indent=2))
    return filepath


def load_research_run(run_id: str) -> ResearchRunResult:
    """Loads a named ResearchRunResult JSON file."""
    filepath = os.path.join(_ARTIFACT_DIR, f"{run_id}.json")
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Research run artifact '{run_id}' not found.")
    with open(filepath, "r") as f:
        data = json.load(f)
    return ResearchRunResult(**data)


def save_calibration_report(report: CalibrationReport) -> str:
    """Saves a CalibrationReport JSON artifact."""
    os.makedirs(_ARTIFACT_DIR, exist_ok=True)
    filepath = os.path.join(_ARTIFACT_DIR, f"{report.report_id}.json")
    with open(filepath, "w") as f:
        f.write(report.model_dump_json(indent=2))
    return filepath


def compile_calibration_html(report: CalibrationReport) -> str:
    """Renders the calibration report down to an HTML file using Jinja2."""
    env = Environment(loader=FileSystemLoader(_TEMPLATE_DIR))
    template = env.get_template("calibration_report_template.html")

    html_content = template.render(report=report, now=datetime.now())

    os.makedirs(_ARTIFACT_DIR, exist_ok=True)
    filepath = os.path.join(_ARTIFACT_DIR, f"{report.report_id}.html")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)

    return filepath
