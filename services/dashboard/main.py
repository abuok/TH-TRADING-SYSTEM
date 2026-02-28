import os
import json
import sys
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
from sqlalchemy.orm import Session
from typing import List, Optional

# Ensure the root directory is in the sys.path for importing shared
sys.path.append(os.getcwd())

import shared.database.session as db_session
from shared.database.models import Packet, IncidentLog, KillSwitch, SessionBriefing, GuardrailsLog, PolicySelectionLog, ActionItem, OpsReportLog, OrderTicket, LiveQuote, SymbolSpec
from services.dashboard.logic import get_service_health, get_dashboard_data, get_tickets, get_briefings, get_latest_briefing
from shared.logic.sessions import get_nairobi_time
from sqlalchemy import func, and_
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets

security = HTTPBasic()

app = FastAPI(title="Tradehall Trading System")

# Templates setup (optional in lightweight test environments)
try:
    templates = Jinja2Templates(directory="services/dashboard/templates")
except AssertionError:
    templates = None


def render_template(template_name: str, context: dict):
    if templates is not None:
        return templates.TemplateResponse(template_name, context)

    if template_name == "index.html":
        health = context.get("health", {})
        kill_switches = context.get("kill_switches", [])
        setups = context.get("latest_setups", [])
        parts = ["<h1>System Overview</h1>", " ".join(health.keys())]
        for ks in kill_switches:
            parts.append(f"{getattr(ks, 'switch_type', '')} {getattr(ks, 'target', None) or 'GLOBAL'}")
        for s in setups:
            if isinstance(s, dict):
                label = "Stale" if not s.get("is_fresh", True) else "Fresh"
                parts.append(f"{s.get('asset_pair', '')} {label}")
        body = " ".join([p for p in parts if p])
    else:
        safe_context = {k: v for k, v in context.items() if k != "request"}
        body = f"<h1>{template_name}</h1><pre>{json.dumps(str(safe_context))}</pre>"

    return HTMLResponse(f"<!doctype html><html><body>{body}</body></html>")

# Mount artifacts directory to serve daily reports
if os.path.exists("artifacts"):
    app.mount("/dashboard/reports/static", StaticFiles(directory="artifacts"), name="reports_static")

if os.path.exists("services/dashboard/static"):
    app.mount("/static", StaticFiles(directory="services/dashboard/static"), name="static")

def verify_auth(request: Request):
    if not os.getenv("DASHBOARD_AUTH_ENABLED", "false").lower() == "true":
        return True
    
    # Manually get credentials to avoid Mandatory Basic Auth popup when disabled
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    import base64
    try:
        scheme, credentials = auth_header.split()
        if scheme.lower() != 'basic': raise ValueError()
        decoded = base64.b64decode(credentials).decode("ascii")
        username, _, password = decoded.partition(":")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid auth header")

    correct_username = os.getenv("DASHBOARD_USERNAME", "admin")
    correct_password = os.getenv("DASHBOARD_PASSWORD")
    
    if not correct_password:
        return True 
        
    is_correct_username = secrets.compare_digest(username, correct_username)
    is_correct_password = secrets.compare_digest(password, correct_password)
    
    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_overview(request: Request, auth: bool = Depends(verify_auth), db: Session = Depends(db_session.get_db)):
    health, response_times = await get_service_health()
    data = get_dashboard_data(db)
    
    return render_template("index.html", {
        "request": request,
        "active_page": "overview",
        "health": health,
        "response_times": response_times,
        **data
    })

@app.get("/dashboard/incidents", response_class=HTMLResponse)
async def dashboard_incidents(request: Request, severity: Optional[str] = None, db: Session = Depends(db_session.get_db)):
    query = db.query(IncidentLog).order_by(IncidentLog.created_at.desc())
    if severity:
        query = query.filter(IncidentLog.severity == severity)
    
    incidents = query.limit(50).all()
    return render_template("incidents.html", {
        "request": request,
        "active_page": "incidents",
        "incidents": incidents
    })

@app.get("/dashboard/setups", response_class=HTMLResponse)
async def dashboard_setups(request: Request, db: Session = Depends(db_session.get_db)):
    from datetime import datetime, timezone
    packets = db.query(Packet).filter(Packet.packet_type == "TechnicalSetupPacket").order_by(Packet.created_at.desc()).limit(50).all()
    
    # Process freshness
    for p in packets:
        p.is_fresh = (datetime.now(timezone.utc) - p.created_at.replace(tzinfo=timezone.utc)).total_seconds() < 60

    return render_template("setups.html", {
        "request": request,
        "active_page": "setups",
        "setups": packets
    })

@app.get("/dashboard/risk", response_class=HTMLResponse)
async def dashboard_risk(request: Request, db: Session = Depends(db_session.get_db)):
    packets = db.query(Packet).filter(Packet.packet_type == "RiskApprovalPacket").order_by(Packet.created_at.desc()).limit(50).all()
    return render_template("risk.html", {
        "request": request,
        "active_page": "risk",
        "decisions": packets
    })

@app.get("/dashboard/reports", response_class=HTMLResponse)
async def dashboard_reports(request: Request):
    reports = []
    if os.path.exists("artifacts"):
        reports = [f for f in os.listdir("artifacts") if f.endswith(".html")]
    
    return render_template("reports.html", {
        "request": request,
        "active_page": "reports",
        "reports": sorted(reports, reverse=True)
    })

@app.get("/dashboard/reports/{filename}")
async def get_report(filename: str):
    if not filename.endswith(".html"):
        raise HTTPException(status_code=400, detail="Invalid report format")
    report_path = os.path.join("artifacts", filename)
    if not os.path.exists(report_path):
        raise HTTPException(status_code=404, detail="Report not found")
    from fastapi.responses import FileResponse
    return FileResponse(report_path)

@app.get("/dashboard/research", response_class=HTMLResponse)
async def dashboard_research(request: Request):
    runs = []
    import json
    if os.path.exists("artifacts/research"):
        files = [f for f in os.listdir("artifacts/research") if f.endswith(".json")]
        for f in sorted(files, reverse=True):
            try:
                with open(os.path.join("artifacts/research", f), "r") as rfile:
                    data = json.load(rfile)
                    runs.append(data)
            except Exception:
                pass

    return render_template("research.html", {
        "request": request,
        "active_page": "research",
        "runs": runs
    })

@app.get("/dashboard/research/{run_id}", response_class=HTMLResponse)
async def research_report_view(run_id: str):
    report_path = os.path.join("artifacts", "research", f"{run_id}.html")
    from fastapi.responses import FileResponse
    if not os.path.exists(report_path):
        raise HTTPException(status_code=404, detail="Research report not found")
    return FileResponse(report_path)

@app.get("/dashboard/calibration", response_class=HTMLResponse)
async def dashboard_calibration(request: Request):
    reports = []
    import json
    if os.path.exists("artifacts/research"):
        files = [f for f in os.listdir("artifacts/research") if f.startswith("cal_") and f.endswith(".json")]
        for f in sorted(files, reverse=True):
            try:
                with open(os.path.join("artifacts/research", f), "r") as rfile:
                    data = json.load(rfile)
                    reports.append(data)
            except Exception:
                pass

    return render_template("calibration.html", {
        "request": request,
        "active_page": "calibration",
        "reports": reports
    })

@app.get("/dashboard/calibration/{report_id}", response_class=HTMLResponse)
async def calibration_report_view(report_id: str):
    report_path = os.path.join("artifacts", "research", f"{report_id}.html")
    from fastapi.responses import FileResponse
    if not os.path.exists(report_path):
        raise HTTPException(status_code=404, detail="Calibration report not found")
    return FileResponse(report_path)


@app.get("/dashboard/tickets", response_class=HTMLResponse)
async def tickets(request: Request, pair: Optional[str] = None):
    ticket_list = await get_tickets(pair)
    return render_template("tickets.html", {
        "request": request,
        "active_page": "tickets",
        "tickets": ticket_list,
        "selected_pair": pair,
    })


@app.get("/dashboard/briefings", response_class=HTMLResponse)
async def dashboard_briefings(request: Request, db: Session = Depends(db_session.get_db)):
    briefing_list = get_briefings(db)
    latest = get_latest_briefing(db)
    return render_template("briefings.html", {
        "request": request,
        "active_page": "briefings",
        "briefings": briefing_list,
        "latest": latest,
    })


@app.get("/dashboard/briefings/{briefing_id}", response_class=HTMLResponse)
async def dashboard_briefing_detail(briefing_id: str, request: Request, db: Session = Depends(db_session.get_db)):
    record = db.query(SessionBriefing).filter(
        SessionBriefing.briefing_id == briefing_id
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Briefing not found")
    # Read the pre-rendered HTML artifact if it exists
    html_content = None
    if record.html_path and os.path.exists(record.html_path):
        with open(record.html_path, encoding="utf-8") as f:
            html_content = f.read()
    return render_template("briefing_detail.html", {
        "request": request,
        "active_page": "briefings",
        "record": record,
        "html_content": html_content,
    })


@app.get("/dashboard/briefings/{briefing_id}/print", response_class=HTMLResponse)
async def briefing_print_view(briefing_id: str, db: Session = Depends(db_session.get_db)):
    """Returns raw HTML artifact for print — no nav chrome."""
    record = db.query(SessionBriefing).filter(
        SessionBriefing.briefing_id == briefing_id
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Briefing not found")
    if record.html_path and os.path.exists(record.html_path):
        with open(record.html_path, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    raise HTTPException(status_code=404, detail="HTML artifact not found")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "dashboard"}

@app.get("/dashboard/fundamentals", response_class=HTMLResponse)
async def dashboard_fundamentals(request: Request, db: Session = Depends(db_session.get_db)):
    # Latest movers sync
    movers = db.query(Packet).filter(
        Packet.packet_type == "MarketMoversPacket"
    ).order_by(Packet.created_at.desc()).first()

    # Get latest pair bias for XAUUSD and GBPJPY
    pairs_data = {}
    for pair in ["XAUUSD", "GBPJPY"]:
        recent = db.query(Packet).filter(
            Packet.packet_type == "PairFundamentalsPacket",
            Packet.data["asset_pair"].as_string() == pair
        ).order_by(Packet.created_at.desc()).limit(10).all()
        pairs_data[pair] = recent

    return render_template("fundamentals.html", {
        "request": request,
        "active_page": "fundamentals",
        "movers": movers,
        "pairs_data": pairs_data
    })

@app.get("/dashboard/guardrails/{setup_id}", response_class=HTMLResponse)
async def guardrails_detail(
    setup_id: str, request: Request, db: Session = Depends(db_session.get_db)
):
    """Display guardrails rule checks for a specific setup packet."""
    # Try to resolve as int (DB id) first, fallback to pair string search
    try:
        setup_packet_id = int(setup_id)
        record = db.query(GuardrailsLog).filter(
            GuardrailsLog.setup_packet_id == setup_packet_id
        ).order_by(GuardrailsLog.created_at.desc()).first()
    except ValueError:
        record = db.query(GuardrailsLog).filter(
            GuardrailsLog.pair == setup_id
        ).order_by(GuardrailsLog.created_at.desc()).first()

    result = record.result_json if record else None
    pair = record.pair if record else setup_id

    return render_template("guardrails_detail.html", {
        "request": request,
        "active_page": "setups",
        "setup_id": setup_id,
        "pair": pair,
        "result": result,
    })

@app.get("/dashboard/queue", response_class=HTMLResponse)
async def dashboard_queue(request: Request):
    return render_template("queue.html", {
        "request": request,
        "active_page": "queue",
    })
# --- Manual Review Queue Endpoints ---
from pydantic import BaseModel
from shared.types.trading import SkipReasonEnum, TicketOutcomeEnum
from services.tickets.queue_logic import approve_ticket, skip_ticket, close_ticket, auto_expire_tickets
from shared.types.execution_prep import ExecutionPrepSchema
from services.orchestration.logic.execution_prep_generator import ExecutionPrepGenerator
from shared.database.models import ExecutionPrepLog
from shared.logic.sessions import get_nairobi_time

class SkipPayload(BaseModel):
    reason: SkipReasonEnum
    notes: Optional[str] = None

class ClosePayload(BaseModel):
    outcome: TicketOutcomeEnum
    exit_price: Optional[float] = None
    realized_r: Optional[float] = None
    screenshot_ref: Optional[str] = None

@app.get("/api/tickets/queue")
async def get_review_queue(db: Session = Depends(db_session.get_db)):
    auto_expire_tickets(db) # Expire stale tickets on load
    tickets = db.query(OrderTicket).filter(
        OrderTicket.status == "IN_REVIEW"
    ).order_by(
        OrderTicket.expires_at.asc(),
        OrderTicket.guardrails_score.desc()
    ).all()
    return tickets

@app.get("/api/tickets/stats")
async def get_queue_stats(date_str: Optional[str] = None, db: Session = Depends(db_session.get_db)):
    d = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else datetime.now(timezone.utc).date()
    # Simple count aggregates
    query = db.query(OrderTicket).filter(func.date(OrderTicket.created_at) == d)
    
    approved = query.filter(OrderTicket.status == "APPROVED").count()
    skipped = query.filter(OrderTicket.status == "SKIPPED").count()
    expired = query.filter(OrderTicket.status == "EXPIRED").count()
    closed_tickets = query.filter(OrderTicket.status == "CLOSED").all()
    
    avg_r = sum(t.manual_outcome_r for t in closed_tickets if t.manual_outcome_r) / len(closed_tickets) if closed_tickets else 0
    
    return {
        "date": str(d),
        "approved": approved,
        "skipped": skipped,
        "expired": expired,
        "closed": len(closed_tickets),
        "avg_r": round(avg_r, 2)
    }

@app.post("/api/tickets/{ticket_id}/approve")
async def api_approve_ticket(ticket_id: str, db: Session = Depends(db_session.get_db)):
    try:
        t = approve_ticket(db, ticket_id)
        
        # Generate Execution Prep
        generator = ExecutionPrepGenerator(db)
        # The generator/preflight will now pull live data from the bridge
        prep = generator.generate(t)
        
        log = ExecutionPrepLog(
            prep_id=prep.prep_id,
            ticket_id=t.ticket_id,
            expires_at=prep.expires_at,
            data=prep.model_dump(mode="json"),
            status="ACTIVE"
        )
        db.add(log)
        db.commit()
        
        return {"status": "success", "ticket": t.ticket_id, "prep_id": prep.prep_id}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/execution-prep/{ticket_id}", response_model=ExecutionPrepSchema)
async def get_execution_prep(ticket_id: str, db: Session = Depends(db_session.get_db)):
    prep_log = db.query(ExecutionPrepLog).filter(ExecutionPrepLog.ticket_id == ticket_id).order_by(ExecutionPrepLog.created_at.desc()).first()
    if not prep_log:
        raise HTTPException(status_code=404, detail="Execution prep not found")
    
    prep_data = ExecutionPrepSchema(**prep_log.data)
    # Update status if expired
    if get_nairobi_time() > prep_data.expires_at and prep_log.status == "ACTIVE":
        prep_log.status = "EXPIRED"
        db.commit()
        prep_data.status = "EXPIRED"
    else:
        prep_data.status = prep_log.status
        
    return prep_data


@app.post("/api/execution-prep/{ticket_id}/override")
async def override_execution_prep(ticket_id: str, reason: str, db: Session = Depends(db_session.get_db)):
    prep_log = db.query(ExecutionPrepLog).filter(ExecutionPrepLog.ticket_id == ticket_id).order_by(ExecutionPrepLog.created_at.desc()).first()
    if not prep_log:
        raise HTTPException(status_code=404, detail="Execution prep not found")
    
    prep_log.status = "OVERRIDDEN"
    prep_log.override_reason = reason
    db.commit()
    return {"status": "success"}

@app.post("/api/tickets/{ticket_id}/skip")
async def api_skip_ticket(ticket_id: str, payload: SkipPayload, db: Session = Depends(db_session.get_db)):
    try:
        t = skip_ticket(db, ticket_id, payload.reason, payload.notes)
        return {"status": "success", "ticket": t.ticket_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/tickets/{ticket_id}/close")
async def api_close_ticket(ticket_id: str, payload: ClosePayload, db: Session = Depends(db_session.get_db)):
    try:
        t = close_ticket(db, ticket_id, payload.outcome, payload.exit_price, payload.realized_r, payload.screenshot_ref)
        return {"status": "success", "ticket": t.ticket_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# --- Hindsight Evaluation Endpoints ---
from services.research.hindsight import run_hindsight_for_date, get_hindsight_summary, generate_hindsight_report

@app.post("/api/hindsight/run")
async def api_hindsight_run(date_str: str, db: Session = Depends(db_session.get_db)):
    # Simple hardcode for demonstration. Normally map string -> path.
    csv_path = "./data.csv"
    if not os.path.exists(csv_path):
        return {"error": "CSV data not found for deterministic hindsight."}
        
    res = run_hindsight_for_date(db, date_str, csv_path)
    report_path = generate_hindsight_report(db, date_str)
    return {
        "status": "success", 
        "processed": res.get("processed"), 
        "report_generated": bool(report_path)
    }

@app.get("/api/hindsight/summary")
async def api_hindsight_summary(date_str: str, db: Session = Depends(db_session.get_db)):
    return get_hindsight_summary(db, date_str)

@app.get("/dashboard/hindsight", response_class=HTMLResponse)
async def dashboard_hindsight(request: Request, date_str: Optional[str] = None, db: Session = Depends(db_session.get_db)):
    date_val = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    summary = get_hindsight_summary(db, date_val)
    
    parsed_date = datetime.strptime(date_val, "%Y-%m-%d").date()
    # Get the tickets that have hindsight done for this date
    tickets = db.query(OrderTicket).filter(
        func.date(OrderTicket.created_at) == parsed_date,
        OrderTicket.hindsight_status == "DONE"
    ).all()
    
    return render_template("hindsight.html", {
        "request": request,
        "active_page": "hindsight",
        "date_str": date_val,
        "summary": summary,
        "tickets": tickets
    })

@app.get("/dashboard/policies", response_class=HTMLResponse)
async def dashboard_policies(request: Request, auth: bool = Depends(verify_auth), db: Session = Depends(db_session.get_db)):
    from sqlalchemy import func
    # Latest policy per pair
    subq = db.query(
        PolicySelectionLog.pair,
        func.max(PolicySelectionLog.created_at).label("max_ts")
    ).group_by(PolicySelectionLog.pair).subquery()
    
    active_policies = db.query(PolicySelectionLog).join(
        subq, 
        and_(
            PolicySelectionLog.pair == subq.c.pair,
            PolicySelectionLog.created_at == subq.c.max_ts
        )
    ).all()

    history = db.query(PolicySelectionLog).order_by(
        PolicySelectionLog.created_at.desc()
    ).limit(30).all()

    return render_template("policies.html", {
        "request": request,
        "active_page": "policies",
        "active_policies": active_policies,
        "history": history
    })

@app.get("/dashboard/ops/daily", response_class=HTMLResponse)
async def dashboard_daily_ops(request: Request, auth: bool = Depends(verify_auth), db: Session = Depends(db_session.get_db)):
    latest = db.query(OpsReportLog).filter(OpsReportLog.report_type == "daily").order_by(OpsReportLog.created_at.desc()).first()
    if not latest:
        raise HTTPException(status_code=404, detail="No daily report found")
    return render_template("ops_daily_template.html", {"request": request, "report": latest.report_data, "active_page": "ops"})

@app.get("/dashboard/ops/weekly", response_class=HTMLResponse)
async def dashboard_weekly_review(request: Request, auth: bool = Depends(verify_auth), db: Session = Depends(db_session.get_db)):
    latest = db.query(OpsReportLog).filter(OpsReportLog.report_type == "weekly").order_by(OpsReportLog.created_at.desc()).first()
    if not latest:
        raise HTTPException(status_code=404, detail="No weekly report found")
    return render_template("ops_weekly_template.html", {"request": request, "report": latest.report_data, "active_page": "ops"})

@app.get("/dashboard/action-items", response_class=HTMLResponse)
async def dashboard_action_items(request: Request, auth: bool = Depends(verify_auth), db: Session = Depends(db_session.get_db)):
    items = db.query(ActionItem).order_by(ActionItem.created_at.desc()).all()
    return render_template("action_items.html", {"request": request, "items": items, "active_page": "actions"})

@app.post("/api/action-items/{id}/done")
async def mark_action_item_done(id: int, auth: bool = Depends(verify_auth), db: Session = Depends(db_session.get_db)):
    item = db.query(ActionItem).get(id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    item.status = "DONE"
    db.commit()
    return {"status": "success"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)
