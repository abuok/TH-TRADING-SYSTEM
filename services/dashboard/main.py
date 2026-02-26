import os
import sys
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from typing import List, Optional

# Ensure the root directory is in the sys.path for importing shared
sys.path.append(os.getcwd())

import shared.database.session as db_session
from shared.database.models import Packet, IncidentLog, KillSwitch, SessionBriefing, GuardrailsLog
from services.dashboard.logic import get_service_health, get_dashboard_data, get_tickets, get_briefings, get_latest_briefing
from shared.logic.sessions import get_nairobi_time

app = FastAPI(title="Operator Dashboard")

# Templates setup
templates = Jinja2Templates(directory="services/dashboard/templates")

# Mount artifacts directory to serve daily reports
if os.path.exists("artifacts"):
    app.mount("/dashboard/reports/static", StaticFiles(directory="artifacts"), name="reports_static")

if os.path.exists("services/dashboard/static"):
    app.mount("/static", StaticFiles(directory="services/dashboard/static"), name="static")

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_overview(request: Request, db: Session = Depends(db_session.get_db)):
    health, response_times = await get_service_health()
    data = get_dashboard_data(db)
    
    return templates.TemplateResponse("index.html", {
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
    return templates.TemplateResponse("incidents.html", {
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

    return templates.TemplateResponse("setups.html", {
        "request": request,
        "active_page": "setups",
        "setups": packets
    })

@app.get("/dashboard/risk", response_class=HTMLResponse)
async def dashboard_risk(request: Request, db: Session = Depends(db_session.get_db)):
    packets = db.query(Packet).filter(Packet.packet_type == "RiskApprovalPacket").order_by(Packet.created_at.desc()).limit(50).all()
    return templates.TemplateResponse("risk.html", {
        "request": request,
        "active_page": "risk",
        "decisions": packets
    })

@app.get("/dashboard/reports", response_class=HTMLResponse)
async def dashboard_reports(request: Request):
    reports = []
    if os.path.exists("artifacts"):
        reports = [f for f in os.listdir("artifacts") if f.endswith(".html")]
    
    return templates.TemplateResponse("reports.html", {
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

    return templates.TemplateResponse("research.html", {
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

    return templates.TemplateResponse("calibration.html", {
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
    return templates.TemplateResponse("tickets.html", {
        "request": request,
        "active_page": "tickets",
        "tickets": ticket_list,
        "selected_pair": pair,
    })


@app.get("/dashboard/briefings", response_class=HTMLResponse)
async def dashboard_briefings(request: Request, db: Session = Depends(db_session.get_db)):
    briefing_list = get_briefings(db)
    latest = get_latest_briefing(db)
    return templates.TemplateResponse("briefings.html", {
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
    return templates.TemplateResponse("briefing_detail.html", {
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

    return templates.TemplateResponse("fundamentals.html", {
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

    return templates.TemplateResponse("guardrails_detail.html", {
        "request": request,
        "active_page": "setups",
        "setup_id": setup_id,
        "pair": pair,
        "result": result,
    })

@app.get("/dashboard/queue", response_class=HTMLResponse)
async def dashboard_queue(request: Request):
    return templates.TemplateResponse("queue.html", {
        "request": request,
        "active_page": "queue",
    })

# --- Manual Review Queue Endpoints ---
from pydantic import BaseModel
from shared.types.trading import SkipReasonEnum, TicketOutcomeEnum
from services.tickets.queue_logic import approve_ticket, skip_ticket, close_ticket, auto_expire_tickets

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
        return {"status": "success", "ticket": t.ticket_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

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
    
    return templates.TemplateResponse("hindsight.html", {
        "request": request,
        "active_page": "hindsight",
        "date_str": date_val,
        "summary": summary,
        "tickets": tickets
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)
