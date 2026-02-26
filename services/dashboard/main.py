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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)
