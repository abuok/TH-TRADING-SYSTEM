from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, status
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
import shared.database.session as db_session
from .models import JournalSetup, JournalRiskDecision, JournalTradeOutcome, JournalTicket, JournalTicketTransition
from shared.types.packets import TechnicalSetupPacket, RiskApprovalPacket
from shared.types.trading import OrderTicketSchema
from typing import Optional
from datetime import datetime, timedelta, timezone

import asyncio
from shared.logic.notifications import NotificationService, ConsoleNotificationAdapter

notifier = NotificationService([ConsoleNotificationAdapter()])

@asynccontextmanager
async def lifespan(app: FastAPI):
    db_session.init_db()
    asyncio.create_task(mark_missed_setups())
    yield

app = FastAPI(title="Journal Service", lifespan=lifespan)

@app.get("/health")
def health_check(db: Session = Depends(db_session.get_db)):
    try:
        # Check DB
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unhealthy", "database": str(e)}
        )

async def mark_missed_setups():
    """Background task to mark un-taken setups as MISSED after 15 minutes."""
    while True:
        try:
            db = db_session.SessionLocal()
            timeout_limit = datetime.now(timezone.utc) - timedelta(minutes=15)
            # Mark PENDING setups older than 15 mins as MISSED
            pending = db.query(JournalSetup).filter(
                JournalSetup.status == "PENDING",
                JournalSetup.timestamp < timeout_limit
            ).all()
            for setup in pending:
                setup.status = "MISSED"
            db.commit()
            db.close()
        except Exception as e:
            print(f"Error marking missed setups: {e}")
        await asyncio.sleep(60)

def get_score_label(score: float) -> str:
    if score >= 90:
        return "A+"
    if score >= 70:
        return "B"
    return "C"

@app.post("/log/setup")
def log_setup(setup: TechnicalSetupPacket, score: float, db: Session = Depends(db_session.get_db)):
    db_setup = JournalSetup(
        request_id=f"setup_{datetime.now().timestamp()}",
        asset_pair=setup.asset_pair,
        strategy_name=setup.strategy_name,
        entry_price=setup.entry_price,
        stop_loss=setup.stop_loss,
        take_profit=setup.take_profit,
        timeframe=setup.timeframe,
        setup_score=score,
        score_label=get_score_label(score),
        status="PENDING",
        metadata_json=setup.session_levels
    )
    db.add(db_setup)
    db.commit()
    db.refresh(db_setup)
    return {"id": db_setup.id, "status": "logged", "label": db_setup.score_label}

@app.post("/log/risk_decision")
def log_risk_decision(decision: RiskApprovalPacket, setup_id: Optional[int] = None, db: Session = Depends(db_session.get_db)):
    db_decision = JournalRiskDecision(
        setup_id=setup_id,
        request_id=decision.request_id,
        status=decision.status,
        is_approved=decision.is_approved,
        rr_ratio=decision.rr_ratio,
        reasons=decision.reasons
    )
    db.add(db_decision)
    db.commit()
    return {"status": "decision_logged"}

@app.post("/log/outcome")
def log_outcome(setup_id: int, is_win: bool, r_multiple: float, pnl: float, notes: Optional[str] = None, db: Session = Depends(db_session.get_db)):
    db_outcome = JournalTradeOutcome(
        setup_id=setup_id,
        is_win=is_win,
        r_multiple=r_multiple,
        pnl=pnl,
        notes=notes
    )
    db.add(db_outcome)
    
    # Also update setup status
    setup = db.query(JournalSetup).filter(JournalSetup.id == setup_id).first()
    if setup:
        setup.status = "TAKEN"
        
    db.commit()
    return {"status": "outcome_logged"}

@app.post("/log/ticket")
def log_ticket(ticket: OrderTicketSchema, setup_id: Optional[int] = None, risk_decision_id: Optional[int] = None, db: Session = Depends(db_session.get_db)):
    db_ticket = JournalTicket(
        ticket_id=ticket.ticket_id,
        setup_id=setup_id,
        risk_decision_id=risk_decision_id,
        status=ticket.status,
        plan_snapshot=ticket.model_dump()
    )
    db.add(db_ticket)
    db.commit()
    return {"status": "ticket_logged"}

@app.post("/log/ticket_transition")
def log_ticket_transition(
    ticket_id: str, 
    transition_type: str, 
    details: dict,
    db: Session = Depends(db_session.get_db)
):
    # Idempotency check: don't log the same transition twice
    existing = db.query(JournalTicketTransition).filter(
        JournalTicketTransition.ticket_id == ticket_id,
        JournalTicketTransition.transition_type == transition_type
    ).first()
    
    if existing:
        return {"status": "already_logged"}

    db_transition = JournalTicketTransition(
        ticket_id=ticket_id,
        transition_type=transition_type,
        details_json=details
    )
    db.add(db_transition)
    db.commit()
    return {"status": "transition_logged"}

@app.get("/report/daily", response_class=HTMLResponse)
def daily_report(db: Session = Depends(db_session.get_db)):
    notifier.notify("Daily Trading Journal Report is ready for review.", level="SUCCESS")
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    setups = db.query(JournalSetup).filter(JournalSetup.timestamp >= today).all()
    outcomes = db.query(JournalTradeOutcome).filter(JournalTradeOutcome.timestamp >= today).all()
    
    # Calculate stats
    total_setups = len(setups)
    missed_aplus = sum(1 for s in setups if s.score_label == "A+" and s.status == "MISSED")
    taken_c = sum(1 for s in setups if s.score_label == "C" and s.status == "TAKEN")
    
    # Rule violation cost estimate (simplified: if blocked by risk but taken anyway, or if missed an A+ setup)
    # Let's define it as: (Missed A+ count * avg RR * $10) - (Taken C losses * lot size * leverage)
    potential_profit_missed = sum(s.setup_score / 20.0 for s in setups if s.score_label == "A+" and s.status == "MISSED")
    violation_cost = potential_profit_missed # For demo
    
    total_pnl = sum(o.pnl for o in outcomes)
    
    html_content = f"""
    <html>
        <head>
            <title>Enhanced Daily Trading Journal Report</title>
            <style>
                body {{ font-family: sans-serif; margin: 40px; background: #fdfdfd; color: #333; }}
                h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
                .stats {{ display: flex; flex-wrap: wrap; gap: 20px; margin-bottom: 30px; }}
                .stat-card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); min-width: 150px; flex: 1; }}
                .stat-card h3 {{ margin-top: 0; color: #7f8c8d; font-size: 0.9em; }}
                .stat-card p {{ font-size: 1.5em; font-weight: bold; margin: 5px 0 0; color: #2c3e50; }}
                .alert {{ color: #e74c3c; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 20px; background: white; }}
                th, td {{ padding: 12px; border: 1px solid #eee; text-align: left; }}
                th {{ background: #f8f9fa; color: #34495e; }}
                .status-pending {{ background: #fff3cd; color: #856404; }}
                .status-taken {{ background: #d4edda; color: #155724; }}
                .status-missed {{ background: #f8d7da; color: #721c24; }}
            </style>
        </head>
        <body>
            <h1>Daily Performance Report - {today.strftime('%Y-%m-%d')}</h1>
            
            <div class="stats">
                <div class="stat-card"><h3>Total Setups</h3><p>{total_setups}</p></div>
                <div class="stat-card"><h3>Missed A+</h3><p class="alert">{missed_aplus}</p></div>
                <div class="stat-card"><h3>Taken C</h3><p>{taken_c}</p></div>
                <div class="stat-card"><h3>Potential Profit Missed</h3><p class="alert">${violation_cost:.2f}</p></div>
                <div class="stat-card"><h3>Actual PnL</h3><p style="color: {'green' if total_pnl >=0 else 'red'}">${total_pnl:.2f}</p></div>
            </div>
            
            <h2>Journal Log</h2>
            <table>
                <tr><th>Timestamp</th><th>Pair</th><th>Label</th><th>Status</th><th>Score</th></tr>
                {"".join([f"<tr><td>{s.timestamp.strftime('%H:%M')}</td><td>{s.asset_pair}</td><td>{s.score_label}</td><td class='status-{s.status.lower()}'>{s.status}</td><td>{s.setup_score}</td></tr>" for s in setups])}
            </table>
        </body>
    </html>
    """
    return html_content

@app.get("/report/weekly", response_class=HTMLResponse)
def weekly_report(db: Session = Depends(db_session.get_db)):
    now = datetime.now(timezone.utc)
    one_week_ago = now - timedelta(days=7)
    outcomes = db.query(JournalTradeOutcome).filter(JournalTradeOutcome.timestamp >= one_week_ago).all()
    
    total_pnl = sum(o.pnl for o in outcomes)
    avg_r = sum(o.r_multiple for o in outcomes) / len(outcomes) if outcomes else 0
    
    return f"<h1>Weekly Summary</h1><p>Total PnL: ${total_pnl:.2f}</p><p>Avg R-multiple: {avg_r:.2f}</p>"


@app.post("/log/guardrails", status_code=201)
async def log_guardrails(payload: dict, db: Session = Depends(db_session.get_db)):
    """
    Persist a GuardrailsResult to the guardrails_logs table.
    Called by the Orchestrator after each evaluation.
    """
    from shared.database.models import GuardrailsLog
    record = GuardrailsLog(
        setup_packet_id=payload.get("setup_packet_id"),
        ticket_id=payload.get("ticket_id"),
        pair=payload.get("pair", "UNKNOWN"),
        discipline_score=payload.get("discipline_score", 0),
        hard_block=payload.get("hard_block", False),
        primary_block_reason=payload.get("primary_block_reason"),
        guardrails_version=payload.get("guardrails_version", "2.0.0"),
        result_json=payload,
    )
    db.add(record)
    db.commit()
    return {"status": "logged", "pair": record.pair, "score": record.discipline_score}
