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
from shared.database.models import Packet, IncidentLog, KillSwitch
from services.dashboard.logic import get_service_health, get_dashboard_data, get_tickets
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
    # Simple redirect to static file
    if not filename.endswith(".html"):
        raise HTTPException(status_code=400, detail="Invalid report format")
    
    report_path = os.path.join("artifacts", filename)
    if not os.path.exists(report_path):
        raise HTTPException(status_code=404, detail="Report not found")
        
    from fastapi.responses import FileResponse
    return FileResponse(report_path)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "dashboard"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)
