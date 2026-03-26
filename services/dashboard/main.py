# ruff: noqa: E402  # delayed imports/path setup required in this module
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Load environment variables
load_dotenv()

from sqlalchemy.orm import Session

# Ensure the root directory is in the sys.path for importing shared
sys.path.append(os.getcwd())

import secrets

from fastapi.security import HTTPBasic
from sqlalchemy import and_, func

import shared.database.session as db_session
from services.dashboard.logic import (
    get_briefings,
    get_dashboard_data,
    get_jarvis_data,
    get_latest_briefing,
    get_service_health,
    get_tickets,
)
from shared.database.models import (
    ActionItem,
    AlignmentLog,
    IncidentLog,
    OpsReportLog,
    OrderTicket,
    Packet,
    PilotScorecardLog,
    PilotSessionLog,
    PolicySelectionLog,
    SessionBriefing,
    TicketTradeLink,
    TradeFillLog,
    TuningProposalLog,
)
from shared.database.models import (
    PositionSnapshot as PositionSnapshotModel,
)
from shared.logic.sessions import get_nairobi_time

security = HTTPBasic()

app = FastAPI(title="Tradehall Trading System")
from shared.ui.theme import ACCENTS, NEUTRALS

# Templates setup
templates = None
if os.path.exists("services/dashboard/templates"):
    templates = Jinja2Templates(directory="services/dashboard/templates")

logger = logging.getLogger("Dashboard")


def render_template(template_name: str, context: dict):
    if templates is not None:
        return templates.TemplateResponse(
            request=context.get("request"), name=template_name, context=context
        )
    # Fallback generic rendering for test environments missing templates
    body = f"<h1>{template_name}</h1>"

    if template_name == "briefings.html":
        body = "<h1>Briefings</h1>"
    else:
        safe_context = {k: v for k, v in context.items() if k != "request"}
        body = f"<h1>{template_name}</h1><pre>{json.dumps(str(safe_context))}</pre>"

    return HTMLResponse(f"<!doctype html><html><body>{body}</body></html>")


# Mount artifacts directory to serve daily reports
if os.path.exists("artifacts"):
    app.mount(
        "/dashboard/reports/static",
        StaticFiles(directory="artifacts"),
        name="reports_static",
    )

if os.path.exists("services/dashboard/static"):
    app.mount(
        "/static", StaticFiles(directory="services/dashboard/static"), name="static"
    )


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
        if scheme.lower() != "basic":
            raise ValueError()
        decoded = base64.b64decode(credentials).decode("ascii")
        username, _, password = decoded.partition(":")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid auth header") from None

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
async def dashboard_overview(
    request: Request,
    auth: bool = Depends(verify_auth),
    db: Session = Depends(db_session.get_db),
):
    health, response_times = await get_service_health()
    data = get_dashboard_data(db)

    return render_template(
        "index.html",
        {
            "request": request,
            "active_page": "overview",
            "health": health,
            "response_times": response_times,
            **data,
        },
    )




@app.get("/dashboard/incidents", response_class=HTMLResponse)
async def dashboard_incidents(
    request: Request,
    severity: str | None = None,
    db: Session = Depends(db_session.get_db),
):
    query = db.query(IncidentLog).order_by(IncidentLog.created_at.desc())
    if severity:
        query = query.filter(IncidentLog.severity == severity)

    incidents = query.limit(50).all()
    return render_template(
        "incidents.html",
        {"request": request, "active_page": "incidents", "incidents": incidents},
    )


@app.get("/dashboard/setups", response_class=HTMLResponse)
async def dashboard_setups(request: Request, db: Session = Depends(db_session.get_db)):
    from datetime import datetime, timezone

    packets = (
        db.query(Packet)
        .filter(Packet.packet_type == "TechnicalSetupPacket")
        .order_by(Packet.created_at.desc())
        .limit(50)
        .all()
    )

    # Process freshness
    for p in packets:
        p.is_fresh = (
            datetime.now(timezone.utc) - p.created_at.replace(tzinfo=timezone.utc)
        ).total_seconds() < 60

    return render_template(
        "setups.html", {"request": request, "active_page": "setups", "setups": packets}
    )


@app.get("/dashboard/risk", response_class=HTMLResponse)
async def dashboard_risk(request: Request, db: Session = Depends(db_session.get_db)):
    packets = (
        db.query(Packet)
        .filter(Packet.packet_type == "RiskApprovalPacket")
        .order_by(Packet.created_at.desc())
        .limit(50)
        .all()
    )
    return render_template(
        "risk.html", {"request": request, "active_page": "risk", "decisions": packets}
    )


@app.get("/dashboard/reports", response_class=HTMLResponse)
async def dashboard_reports(request: Request):
    reports = []
    if os.path.exists("artifacts"):
        reports = [f for f in os.listdir("artifacts") if f.endswith(".html")]

    return render_template(
        "reports.html",
        {
            "request": request,
            "active_page": "reports",
            "reports": sorted(reports, reverse=True),
        },
    )


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

    if os.path.exists("artifacts/research"):
        files = [
            f
            for f in os.listdir("artifacts/research")
            if f.startswith("res_") and f.endswith(".json")
        ]
        for f in sorted(files, reverse=True):
            try:
                with open(os.path.join("artifacts/research", f)) as rfile:
                    data = json.load(rfile)
                    runs.append(data)
            except Exception as e:
                logger.warning(f"Failed to load research report {f}: {e}")

    return render_template(
        "research.html", {"request": request, "active_page": "research", "runs": runs}
    )


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

    if os.path.exists("artifacts/research"):
        files = [
            f
            for f in os.listdir("artifacts/research")
            if f.startswith("cal_") and f.endswith(".json")
        ]
        for f in sorted(files, reverse=True):
            try:
                with open(os.path.join("artifacts/research", f)) as rfile:
                    data = json.load(rfile)
                    reports.append(data)
            except Exception as e:
                logger.warning(f"Failed to load calibration report {f}: {e}")

    return render_template(
        "calibration.html",
        {"request": request, "active_page": "calibration", "reports": reports},
    )


@app.get("/dashboard/calibration/{report_id}", response_class=HTMLResponse)
async def calibration_report_view(report_id: str):
    report_path = os.path.join("artifacts", "research", f"{report_id}.html")
    from fastapi.responses import FileResponse

    if not os.path.exists(report_path):
        raise HTTPException(status_code=404, detail="Calibration report not found")
    return FileResponse(report_path)


@app.get("/dashboard/tuning", response_class=HTMLResponse)
def dashboard_tuning(request: Request, db: Session = Depends(db_session.get_db)):
    verify_auth(request)
    logs = (
        db.query(TuningProposalLog)
        .order_by(TuningProposalLog.created_at.desc())
        .limit(20)
        .all()
    )
    reports = []
    for log in logs:
        reports.append(
            {
                "report_id": log.report_id,
                "created_at": log.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "status": log.status,
                "data": log.data,
            }
        )
    return render_template(
        "tuning.html", {"request": request, "active_page": "tuning", "reports": reports}
    )


from pydantic import BaseModel


class ReviewPayload(BaseModel):
    action: str  # ACCEPT or REJECT
    notes: str = ""


@app.post("/api/tuning/{report_id}/proposals/{prop_id}/review")
def review_proposal(
    report_id: str,
    prop_id: str,
    payload: ReviewPayload,
    request: Request,
    db: Session = Depends(db_session.get_db),
):
    verify_auth(request)
    log = (
        db.query(TuningProposalLog)
        .filter(TuningProposalLog.report_id == report_id)
        .first()
    )
    if not log:
        raise HTTPException(status_code=404, detail="Report not found")

    data = log.data
    prop_found = False
    new_proposals = []

    for p in data.get("proposals", []):
        if p.get("id") == prop_id:
            p["status"] = (
                payload.action
            )  # Add a status field directly to the proposal inside the JSON
            p["reviewer_notes"] = payload.notes
            prop_found = True
        new_proposals.append(p)

    if not prop_found:
        raise HTTPException(status_code=404, detail="Proposal not found in report")

    data["proposals"] = new_proposals
    log.data = data  # SQLAlchemy JSON update

    # Check if all proposals in report are reviewed to update parent log status
    all_reviewed = all(
        p.get("status") in ["ACCEPT", "REJECT"] for p in data["proposals"]
    )
    if all_reviewed:
        log.status = "REVIEWED"

    # Manually trigger SQLAlchemy JSON mutation flagging
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(log, "data")

    db.commit()
    return {"status": "success", "message": f"Proposal marked as {payload.action}"}


@app.get("/dashboard/trades", response_class=HTMLResponse)
async def dashboard_trades(request: Request, db: Session = Depends(db_session.get_db)):
    fills = (
        db.query(TradeFillLog).order_by(TradeFillLog.time_utc.desc()).limit(100).all()
    )
    positions = (
        db.query(PositionSnapshotModel)
        .order_by(PositionSnapshotModel.updated_at_utc.desc())
        .all()
    )

    # Enrich fills with ticket links
    for f in fills:
        link = (
            db.query(TicketTradeLink)
            .filter(TicketTradeLink.broker_trade_id == f.broker_trade_id)
            .first()
        )
        f.ticket_id = link.ticket_id if link else None

    return render_template(
        "trades.html",
        {
            "request": request,
            "active_page": "trades",
            "fills": fills,
            "positions": positions,
        },
    )


@app.get("/dashboard/management", response_class=HTMLResponse)
async def dashboard_management(
    request: Request, db: Session = Depends(db_session.get_db)
):
    from shared.database.models import ManagementSuggestionLog

    suggestions = (
        db.query(ManagementSuggestionLog)
        .order_by(ManagementSuggestionLog.created_at.desc())
        .limit(50)
        .all()
    )
    # Also get open positions for context
    positions = db.query(PositionSnapshotModel).all()

    return render_template(
        "management.html",
        {
            "request": request,
            "active_page": "management",
            "suggestions": [s.data for s in suggestions],  # Using the JSON data field
            "positions": positions,
        },
    )


@app.get("/dashboard/tickets", response_class=HTMLResponse)
async def tickets(request: Request, pair: str | None = None):
    ticket_list = await get_tickets(pair)
    return render_template(
        "tickets.html",
        {
            "request": request,
            "active_page": "tickets",
            "tickets": ticket_list,
            "selected_pair": pair,
        },
    )


@app.get("/dashboard/briefings", response_class=HTMLResponse)
async def dashboard_briefings(
    request: Request, db: Session = Depends(db_session.get_db)
):
    briefing_list = get_briefings(db)
    latest = get_latest_briefing(db)
    return render_template(
        "briefings.html",
        {
            "request": request,
            "active_page": "briefings",
            "briefings": briefing_list,
            "latest": latest,
        },
    )


@app.get("/dashboard/briefings/{briefing_id}", response_class=HTMLResponse)
async def dashboard_briefing_detail(
    briefing_id: str, request: Request, db: Session = Depends(db_session.get_db)
):
    record = (
        db.query(SessionBriefing)
        .filter(SessionBriefing.briefing_id == briefing_id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Briefing not found")
    # Read the pre-rendered HTML artifact if it exists
    html_content = None
    if record.html_path and os.path.exists(record.html_path):
        with open(record.html_path, encoding="utf-8") as f:
            html_content = f.read()
    return render_template(
        "briefing_detail.html",
        {
            "request": request,
            "active_page": "briefings",
            "record": record,
            "html_content": html_content,
        },
    )


@app.get("/dashboard/briefings/{briefing_id}/print", response_class=HTMLResponse)
async def briefing_print_view(
    briefing_id: str, db: Session = Depends(db_session.get_db)
):
    """Returns raw HTML artifact for print — no nav chrome."""
    record = (
        db.query(SessionBriefing)
        .filter(SessionBriefing.briefing_id == briefing_id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Briefing not found")
    if record.html_path and os.path.exists(record.html_path):
        with open(record.html_path, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    raise HTTPException(status_code=404, detail="HTML artifact not found")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "dashboard"}


@app.get("/api/jarvis")
async def api_jarvis(db: Session = Depends(db_session.get_db)):
    """Live intelligence endpoint — powers the Jarvis Command Center frontend."""
    try:
        return get_jarvis_data(db)
    except Exception as e:
        logger.exception("Jarvis API error")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/dashboard/fundamentals", response_class=HTMLResponse)
async def dashboard_fundamentals(
    request: Request, db: Session = Depends(db_session.get_db)
):
    # Latest movers sync
    movers = (
        db.query(Packet)
        .filter(Packet.packet_type == "MarketMoversPacket")
        .order_by(Packet.created_at.desc())
        .first()
    )

    # Get latest pair bias for XAUUSD and GBPJPY
    pairs_data = {}
    for pair in ["XAUUSD", "GBPJPY"]:
        recent = (
            db.query(Packet)
            .filter(
                Packet.packet_type == "PairFundamentalsPacket",
                Packet.data["asset_pair"].as_string() == pair,
            )
            .order_by(Packet.created_at.desc())
            .limit(10)
            .all()
        )
        pairs_data[pair] = recent

    return render_template(
        "fundamentals.html",
        {
            "request": request,
            "active_page": "fundamentals",
            "movers": movers,
            "pairs_data": pairs_data,
        },
    )


@app.get("/dashboard/guardrails/{setup_id}", response_class=HTMLResponse)
async def guardrails_detail(
    setup_id: str, request: Request, db: Session = Depends(db_session.get_db)
):
    """Display guardrails rule checks for a specific setup packet."""
    # Try to resolve as int (DB id) first, fallback to pair string search
    try:
        setup_packet_id = int(setup_id)
        record = (
            db.query(AlignmentLog)
            .filter(AlignmentLog.setup_packet_id == setup_packet_id)
            .order_by(AlignmentLog.created_at.desc())
            .first()
        )
    except ValueError:
        record = (
            db.query(AlignmentLog)
            .filter(AlignmentLog.pair == setup_id)
            .order_by(AlignmentLog.created_at.desc())
            .first()
        )

    result = record.result_json if record else None
    pair = record.pair if record else setup_id

    return render_template(
        "guardrails_detail.html",
        {
            "request": request,
            "active_page": "setups",
            "setup_id": setup_id,
            "pair": pair,
            "result": result,
        },
    )


@app.get("/dashboard/queue", response_class=HTMLResponse)
async def dashboard_queue(request: Request):
    return render_template(
        "queue.html",
        {
            "request": request,
            "active_page": "queue",
        },
    )


# --- Manual Review Queue Endpoints ---
from pydantic import BaseModel

from services.orchestration.logic.execution_prep_generator import ExecutionPrepGenerator
from services.tickets.queue_logic import (
    approve_ticket,
    auto_expire_tickets,
    close_ticket,
    skip_ticket,
)
from shared.database.models import ExecutionPrepLog
from shared.types.execution_prep import ExecutionPrepSchema
from shared.types.trading import SkipReasonEnum, TicketOutcomeEnum


class SkipPayload(BaseModel):
    reason: SkipReasonEnum
    notes: str | None = None


class ClosePayload(BaseModel):
    outcome: TicketOutcomeEnum
    exit_price: float | None = None
    realized_r: float | None = None
    screenshot_ref: str | None = None


@app.get("/api/tickets/queue")
async def get_review_queue(db: Session = Depends(db_session.get_db)):
    auto_expire_tickets(db)  # Expire stale tickets on load
    tickets = (
        db.query(OrderTicket)
        .filter(OrderTicket.status == "IN_REVIEW")
        .order_by(OrderTicket.expires_at.asc(), OrderTicket.guardrails_score.desc())
        .all()
    )
    return tickets


@app.get("/api/tickets/stats")
async def get_queue_stats(
    date_str: str | None = None, db: Session = Depends(db_session.get_db)
):
    d = (
        datetime.strptime(date_str, "%Y-%m-%d").date()
        if date_str
        else datetime.now(timezone.utc).date()
    )
    # Simple count aggregates
    query = db.query(OrderTicket).filter(func.date(OrderTicket.created_at) == d)

    approved = query.filter(OrderTicket.status == "APPROVED").count()
    skipped = query.filter(OrderTicket.status == "SKIPPED").count()
    expired = query.filter(OrderTicket.status == "EXPIRED").count()
    closed_tickets = query.filter(OrderTicket.status == "CLOSED").all()

    avg_r = (
        sum(t.manual_outcome_r for t in closed_tickets if t.manual_outcome_r)
        / len(closed_tickets)
        if closed_tickets
        else 0
    )

    return {
        "date": str(d),
        "approved": approved,
        "skipped": skipped,
        "expired": expired,
        "closed": len(closed_tickets),
        "avg_r": round(avg_r, 2),
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
            status="ACTIVE",
        )
        db.add(log)
        db.commit()

        return {"status": "success", "ticket": t.ticket_id, "prep_id": prep.prep_id}
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/execution-prep/{ticket_id}", response_model=ExecutionPrepSchema)
async def get_execution_prep(ticket_id: str, db: Session = Depends(db_session.get_db)):
    prep_log = (
        db.query(ExecutionPrepLog)
        .filter(ExecutionPrepLog.ticket_id == ticket_id)
        .order_by(ExecutionPrepLog.created_at.desc())
        .first()
    )
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
async def override_execution_prep(
    ticket_id: str, reason: str, db: Session = Depends(db_session.get_db)
):
    prep_log = (
        db.query(ExecutionPrepLog)
        .filter(ExecutionPrepLog.ticket_id == ticket_id)
        .order_by(ExecutionPrepLog.created_at.desc())
        .first()
    )
    if not prep_log:
        raise HTTPException(status_code=404, detail="Execution prep not found")

    prep_log.status = "OVERRIDDEN"
    prep_log.override_reason = reason
    db.commit()
    return {"status": "success"}


@app.post("/api/tickets/{ticket_id}/skip")
async def api_skip_ticket(
    ticket_id: str, payload: SkipPayload, db: Session = Depends(db_session.get_db)
):
    try:
        t = skip_ticket(db, ticket_id, payload.reason, payload.notes)
        return {"status": "success", "ticket": t.ticket_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/api/tickets/{ticket_id}/close")
async def api_close_ticket(
    ticket_id: str, payload: ClosePayload, db: Session = Depends(db_session.get_db)
):
    try:
        t = close_ticket(
            db,
            ticket_id,
            payload.outcome,
            payload.exit_price,
            payload.realized_r,
            payload.screenshot_ref,
        )
        return {"status": "success", "ticket": t.ticket_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# --- Hindsight Evaluation Endpoints ---
from services.research.hindsight import (
    generate_hindsight_report,
    get_hindsight_summary,
    run_hindsight_for_date,
)


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
        "report_generated": bool(report_path),
    }


@app.get("/api/hindsight/summary")
async def api_hindsight_summary(
    date_str: str, db: Session = Depends(db_session.get_db)
):
    return get_hindsight_summary(db, date_str)


@app.get("/dashboard/hindsight", response_class=HTMLResponse)
async def dashboard_hindsight(
    request: Request,
    date_str: str | None = None,
    db: Session = Depends(db_session.get_db),
):
    date_val = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    summary = get_hindsight_summary(db, date_val)

    parsed_date = datetime.strptime(date_val, "%Y-%m-%d").date()
    start_of_day = datetime.combine(
        parsed_date, datetime.min.time(), tzinfo=timezone.utc
    )
    end_of_day = start_of_day + timedelta(days=1)

    # Get the tickets that have hindsight done for this date
    tickets = (
        db.query(OrderTicket)
        .filter(
            OrderTicket.created_at >= start_of_day,
            OrderTicket.created_at < end_of_day,
            OrderTicket.hindsight_status == "DONE",
        )
        .all()
    )

    return render_template(
        "hindsight.html",
        {
            "request": request,
            "active_page": "hindsight",
            "date_str": date_val,
            "summary": summary,
            "tickets": tickets,
        },
    )


@app.get("/dashboard/policies", response_class=HTMLResponse)
async def dashboard_policies(
    request: Request,
    auth: bool = Depends(verify_auth),
    db: Session = Depends(db_session.get_db),
):
    from sqlalchemy import func

    # Latest policy per pair
    subq = (
        db.query(
            PolicySelectionLog.pair,
            func.max(PolicySelectionLog.created_at).label("max_ts"),
        )
        .group_by(PolicySelectionLog.pair)
        .subquery()
    )

    active_policies = (
        db.query(PolicySelectionLog)
        .join(
            subq,
            and_(
                PolicySelectionLog.pair == subq.c.pair,
                PolicySelectionLog.created_at == subq.c.max_ts,
            ),
        )
        .all()
    )

    history = (
        db.query(PolicySelectionLog)
        .order_by(PolicySelectionLog.created_at.desc())
        .limit(30)
        .all()
    )

    return render_template(
        "policies.html",
        {
            "request": request,
            "active_page": "policies",
            "active_policies": active_policies,
            "history": history,
        },
    )


@app.get("/dashboard/ops/daily", response_class=HTMLResponse)
async def dashboard_daily_ops(
    request: Request,
    auth: bool = Depends(verify_auth),
    db: Session = Depends(db_session.get_db),
):
    latest = (
        db.query(OpsReportLog)
        .filter(OpsReportLog.report_type == "daily")
        .order_by(OpsReportLog.created_at.desc())
        .first()
    )
    report_data = latest.report_data if latest else None
    return render_template(
        "ops_daily_template.html",
        {"request": request, "report": report_data, "active_page": "ops"},
    )


@app.get("/dashboard/ops/weekly", response_class=HTMLResponse)
async def dashboard_weekly_review(
    request: Request,
    auth: bool = Depends(verify_auth),
    db: Session = Depends(db_session.get_db),
):
    latest = (
        db.query(OpsReportLog)
        .filter(OpsReportLog.report_type == "weekly")
        .order_by(OpsReportLog.created_at.desc())
        .first()
    )
    report_data = latest.report_data if latest else None
    return render_template(
        "ops_weekly_template.html",
        {"request": request, "report": report_data, "active_page": "ops"},
    )


@app.get("/dashboard/action-items", response_class=HTMLResponse)
async def dashboard_action_items(
    request: Request,
    auth: bool = Depends(verify_auth),
    db: Session = Depends(db_session.get_db),
):
    items = db.query(ActionItem).order_by(ActionItem.created_at.desc()).all()
    return render_template(
        "action_items.html",
        {"request": request, "items": items, "active_page": "actions"},
    )


@app.get("/dashboard/execution-prep", response_class=HTMLResponse)
async def dashboard_execution_prep(
    request: Request,
    db: Session = Depends(db_session.get_db),
):
    preps = (
        db.query(ExecutionPrepLog)
        .order_by(ExecutionPrepLog.created_at.desc())
        .limit(50)
        .all()
    )
    return render_template(
        "execution_prep.html",
        {"request": request, "active_page": "execution-prep", "preps": preps},
    )


@app.get("/dashboard/health", response_class=HTMLResponse)
async def dashboard_health_view(request: Request, db: Session = Depends(db_session.get_db)):
    from services.dashboard.logic import get_service_health
    health, response_times = await get_service_health()
    incidents = db.query(IncidentLog).order_by(IncidentLog.created_at.desc()).limit(20).all()
    
    return render_template(
        "health.html",
        {
            "request": request,
            "active_page": "health",
            "health": health,
            "response_times": response_times,
            "incidents": incidents
        },
    )


@app.get("/dashboard/pilot", response_class=HTMLResponse)
async def dashboard_pilot(request: Request, db: Session = Depends(db_session.get_db)):
    verify_auth(request)
    scorecards = (
        db.query(PilotScorecardLog)
        .order_by(PilotScorecardLog.created_at.desc())
        .limit(10)
        .all()
    )
    sessions = (
        db.query(PilotSessionLog).order_by(PilotSessionLog.date.desc()).limit(15).all()
    )

    return render_template(
        "pilot_index.html",
        {
            "request": request,
            "active_page": "pilot",
            "scorecards": scorecards,
            "recent_sessions": sessions,
        },
    )


@app.get("/dashboard/pilot/gate", response_class=HTMLResponse)
async def dashboard_pilot_gate(request: Request):
    verify_auth(request)
    from services.research.pilot import load_pilot_config

    config = load_pilot_config()
    return render_template(
        "pilot_gate.html",
        {"request": request, "active_page": "pilot", "config": config},
    )


@app.get("/dashboard/pilot/{scorecard_id}", response_class=HTMLResponse)
async def dashboard_pilot_detail(
    scorecard_id: str, request: Request, db: Session = Depends(db_session.get_db)
):
    verify_auth(request)
    log = (
        db.query(PilotScorecardLog)
        .filter(PilotScorecardLog.scorecard_id == scorecard_id)
        .first()
    )
    if not log:
        raise HTTPException(status_code=404, detail="Scorecard not found")

    return render_template(
        "pilot_detail.html",
        {"request": request, "active_page": "pilot", "scorecard": log.data},
    )


@app.post("/api/action-items/{id}/done")
async def mark_action_item_done(
    id: int, auth: bool = Depends(verify_auth), db: Session = Depends(db_session.get_db)
):
    item = db.query(ActionItem).get(id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    item.status = "DONE"
    db.commit()
    return {"status": "success"}


# --- UNIFIED DASHBOARD ROUTES ---

@app.get("/dashboard/order-flow", response_class=HTMLResponse)
async def dashboard_order_flow(
    request: Request,
    auth: bool = Depends(verify_auth),
    db: Session = Depends(db_session.get_db),
):
    # 1. Queue Tickets
    tickets = (
        db.query(OrderTicket)
        .filter(OrderTicket.status == "IN_REVIEW")
        .order_by(OrderTicket.expires_at.asc())
        .limit(20)
        .all()
    )
    # 2. Execution Preps
    preps = (
        db.query(ExecutionPrepLog)
        .order_by(ExecutionPrepLog.created_at.desc())
        .limit(20)
        .all()
    )
    # 3. Trades (Active Positions)
    from shared.database.models import PositionSnapshot, TradeFillLog
    positions = (
        db.query(PositionSnapshotModel)
        .order_by(PositionSnapshotModel.updated_at_utc.desc())
        .all()
    )
    fills = (
        db.query(TradeFillLog).order_by(TradeFillLog.time_utc.desc()).limit(15).all()
    )
    
    return render_template(
        "order_flow.html",
        {
            "request": request,
            "active_page": "order-flow",
            "tickets": tickets,
            "preps": preps,
            "positions": positions,
            "fills": fills,
        },
    )


@app.get("/dashboard/strategy-context", response_class=HTMLResponse)
async def dashboard_strategy_context(
    request: Request,
    auth: bool = Depends(verify_auth),
    db: Session = Depends(db_session.get_db),
):
    # Fundamentals
    movers = (
        db.query(Packet)
        .filter(Packet.packet_type == "MarketMoversPacket")
        .order_by(Packet.created_at.desc())
        .first()
    )
    pairs_data = {}
    for pair in ["XAUUSD", "GBPJPY"]:
        recent = (
            db.query(Packet)
            .filter(
                Packet.packet_type == "PairFundamentalsPacket",
                Packet.data["asset_pair"].as_string() == pair,
            )
            .order_by(Packet.created_at.desc())
            .limit(5)
            .all()
        )
        pairs_data[pair] = recent

    # Pilot
    scorecards = (
        db.query(PilotScorecardLog)
        .order_by(PilotScorecardLog.created_at.desc())
        .limit(10)
        .all()
    )

    return render_template(
        "strategy_context.html",
        {
            "request": request,
            "active_page": "strategy-context",
            "movers": movers,
            "pairs_data": pairs_data,
            "scorecards": scorecards,
        },
    )


@app.get("/dashboard/node-telemetry", response_class=HTMLResponse)
async def dashboard_node_telemetry(
    request: Request,
    auth: bool = Depends(verify_auth),
    db: Session = Depends(db_session.get_db),
):
    from services.dashboard.logic import get_service_health
    
    health, response_times = await get_service_health()
    incidents = db.query(IncidentLog).order_by(IncidentLog.created_at.desc()).limit(20).all()
    
    daily_latest = (
        db.query(OpsReportLog)
        .filter(OpsReportLog.report_type == "daily")
        .order_by(OpsReportLog.created_at.desc())
        .first()
    )
    
    weekly_latest = (
        db.query(OpsReportLog)
        .filter(OpsReportLog.report_type == "weekly")
        .order_by(OpsReportLog.created_at.desc())
        .first()
    )

    return render_template(
        "node_telemetry.html",
        {
            "request": request,
            "active_page": "node-telemetry",
            "health": health,
            "response_times": response_times,
            "incidents": incidents,
            "daily_report": daily_latest.report_data if daily_latest else None,
            "weekly_report": weekly_latest.report_data if weekly_latest else None,
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8005)
