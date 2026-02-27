"""
services/orchestration/main.py
Orchestration Service API — tickets + briefings.
"""
import asyncio
import logging
from fastapi import FastAPI, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timezone

import shared.database.session as db_session
from shared.database.models import OrderTicket, Packet, SessionBriefing
from shared.logic.trading_logic import generate_order_ticket
from shared.logic.briefing import assemble_briefing, persist_briefing
from shared.logic.guardrails import GuardrailsEngine
from shared.logic.fundamentals_engine import evaluate_fundamentals
from shared.logic.sessions import get_nairobi_time, get_session_label, TradingSessions
from shared.logic.notifications import NotificationService, ConsoleNotificationAdapter
from shared.types.packets import TechnicalSetupPacket, RiskApprovalPacket
from shared.types.trading import OrderTicketSchema
from shared.types.guardrails import GuardrailsResult
from shared.logic.policy_router import PolicyRouter
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("OrchestrationAPI")

app = FastAPI(title="Orchestration Service API")
notifier = NotificationService([ConsoleNotificationAdapter()])
_guardrails_engine = GuardrailsEngine()
_policy_router = PolicyRouter()


# ──────────────────────────────────────────────
# DB dependency
# ──────────────────────────────────────────────

def get_db():
    db = db_session.SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ──────────────────────────────────────────────
# Startup — initialise DB and start scheduler
# ──────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    db_session.init_db()
    asyncio.create_task(fundamentals_scheduler())
    asyncio.create_task(briefing_scheduler())

async def fundamentals_scheduler(interval_minutes: int = 30):
    """
    Runs a fundamentals background job every `interval_minutes` to re-score
    XAUUSD and GBPJPY bias based on the latest proxy movements.
    """
    while True:
        try:
            db = next(get_db())
            _run_fundamentals_generation(db)
            db.close()
        except Exception as e:
            logger.error(f"Fundamentals generator error: {e}")
        await asyncio.sleep(interval_minutes * 60)

def _run_fundamentals_generation(db: Session, now: Optional[datetime] = None):
    now = now or get_nairobi_time()
    
    # 1. Fetch latest market context to get proxies and events
    ctx_db = db.query(Packet).filter(
        Packet.packet_type == "MarketContextPacket"
    ).order_by(Packet.created_at.desc()).first()
    
    if not ctx_db:
        logger.warning("No MarketContextPacket available for fundamentals evaluation")
        return
        
    movers, pair_packets = evaluate_fundamentals(ctx_db.data, now)
    
    # Save movers
    db.add(Packet(
        packet_type="MarketMoversPacket",
        created_at=movers.created_at,
        data=movers.model_dump(mode="json")
    ))
    
    # Save pair packets as PairBiasPacket replacement
    for p in pair_packets:
        db.add(Packet(
            packet_type="PairFundamentalsPacket",
            created_at=p.created_at,
            data=p.model_dump(mode="json")
        ))
    db.commit()


async def briefing_scheduler(interval_minutes: int = 30):
    """
    Runs a briefing job every `interval_minutes` during active sessions.
    Pre-session briefing on first entry; intraday deltas afterwards.
    """
    generated_sessions: set = set()
    while True:
        now = get_nairobi_time()
        label = get_session_label(now)
        t = now.time()
        is_active = (
            TradingSessions.is_in_range(t, *TradingSessions.LONDON_RANGE) or
            TradingSessions.is_in_range(t, *TradingSessions.NY_RANGE)
        )
        if is_active:
            session_key = f"{now.date()}-{label}"
            is_delta = session_key in generated_sessions
            try:
                db = db_session.SessionLocal()
                pack = assemble_briefing(db, now_nairobi=now, is_delta=is_delta)
                record = persist_briefing(pack, db)
                generated_sessions.add(session_key)
                db.close()

                # Console notification summary
                top_windows = "; ".join(
                    str(w.get("label", w))
                    for w in pack.market_context.no_trade_windows[:2]
                ) or "None"
                pair_summaries = []
                for po in pack.pair_overviews:
                    t_info = ""
                    if po.latest_ticket:
                        t_info = f" [{po.latest_ticket.status}]"
                    pair_summaries.append(f"{po.pair}: {po.bias}{t_info}")

                msg = (
                    f"{'🔄 DELTA' if pack.is_delta else '🌅 PRE-SESSION'} BRIEFING | "
                    f"{pack.session_label} {pack.date} | "
                    f"No-trade: {top_windows} | "
                    + " | ".join(pair_summaries)
                )
                notifier.notify(msg, level="INFO")
                logger.info(f"Briefing generated: {pack.briefing_id}")
            except Exception as e:
                logger.error(f"Briefing scheduler error: {e}")
        await asyncio.sleep(interval_minutes * 60)


# ──────────────────────────────────────────────
# Health
# ──────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "healthy", "service": "orchestration"}


# ──────────────────────────────────────────────
# Briefing endpoints
# ──────────────────────────────────────────────

@app.post("/briefings/generate")
async def generate_briefing_now(
    is_delta: bool = False, db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Manually trigger a briefing generation."""
    _run_fundamentals_generation(db) # Ensure valid fundamentals before briefing
    now = get_nairobi_time()
    pack = assemble_briefing(db, now_nairobi=now, is_delta=is_delta)
    record = persist_briefing(pack, db)
    return {"briefing_id": record.briefing_id, "html_path": record.html_path}


@app.post("/fundamentals/generate")
async def generate_fundamentals_now(db: Session = Depends(get_db)):
    """Manually trigger a fundamentals evaluation."""
    _run_fundamentals_generation(db)
    return {"status": "generated"}


@app.get("/briefings/latest")
async def get_latest_briefing(db: Session = Depends(get_db)) -> Dict[str, Any]:
    record = db.query(SessionBriefing).order_by(
        SessionBriefing.created_at.desc()
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="No briefings found")
    return {
        "briefing_id": record.briefing_id,
        "session_label": record.session_label,
        "date": str(record.date),
        "is_delta": record.is_delta,
        "html_path": record.html_path,
        "created_at": record.created_at.isoformat(),
    }


@app.get("/briefings")
async def list_briefings(
    limit: int = 20, db: Session = Depends(get_db)
) -> List[Dict[str, Any]]:
    records = db.query(SessionBriefing).order_by(
        SessionBriefing.created_at.desc()
    ).limit(limit).all()
    return [
        {
            "briefing_id": r.briefing_id,
            "session_label": r.session_label,
            "date": str(r.date),
            "is_delta": r.is_delta,
            "html_path": r.html_path,
            "created_at": r.created_at.isoformat(),
        }
        for r in records
    ]


@app.get("/briefings/{briefing_id}")
async def get_briefing(briefing_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    record = db.query(SessionBriefing).filter(
        SessionBriefing.briefing_id == briefing_id
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Briefing not found")
    return {
        "briefing_id": record.briefing_id,
        "session_label": record.session_label,
        "date": str(record.date),
        "is_delta": record.is_delta,
        "html_path": record.html_path,
        "data": record.data,
        "created_at": record.created_at.isoformat(),
    }


# ──────────────────────────────────────────────
# Ticket endpoints
# ──────────────────────────────────────────────

@app.post("/tickets/generate", response_model=OrderTicketSchema)
async def generate_ticket(pair: str, db: Session = Depends(get_db)):
    """Finds the latest setup + risk packet for a pair and creates an OrderTicket."""
    setup_db = db.query(Packet).filter(
        and_(
            Packet.packet_type == "TechnicalSetupPacket",
            Packet.data["asset_pair"].as_string() == pair,
        )
    ).order_by(Packet.created_at.desc()).first()

    if not setup_db:
        raise HTTPException(status_code=404, detail=f"No technical setup found for {pair}")

    risk_db = db.query(Packet).filter(
        and_(
            Packet.packet_type == "RiskApprovalPacket",
            Packet.data["asset_pair"].as_string() == pair,
        )
    ).order_by(Packet.created_at.desc()).first()

    if not risk_db:
        raise HTTPException(status_code=404, detail="No risk decision found for this setup.")

    # Fetch latest market context for news-window check
    ctx_db = db.query(Packet).filter(
        Packet.packet_type == "MarketContextPacket"
    ).order_by(Packet.created_at.desc()).first()
    context_data = ctx_db.data if ctx_db else {}

    # Policy Selection
    # Need movers and pair fundamentals for policy routing
    movers_db = db.query(Packet).filter(Packet.packet_type == "MarketMoversPacket").order_by(Packet.created_at.desc()).first()
    pair_fund_db = db.query(Packet).filter(
        and_(
            Packet.packet_type == "PairFundamentalsPacket",
            Packet.data["asset_pair"].as_string() == pair,
        )
    ).order_by(Packet.created_at.desc()).first()

    movers_data = movers_db.data if movers_db else {}
    pair_fund_data = pair_fund_db.data if pair_fund_db else {}
    
    policy_decision = _policy_router.select_policy(
        movers_data=movers_data,
        context_data=context_data,
        pair_fundamentals=pair_fund_data,
```
    from shared.database.models import PolicySelectionLog
    db.add(PolicySelectionLog(
        primary_block_reason=policy_decision.primary_block_reason,
        policy_name=policy_decision.policy_name,
        policy_hash=policy_decision.policy_hash,
        regime_signals=policy_decision.regime_signals
    ))

    # Run guardrails before ticket generation
    guardrails_result = _guardrails_engine.evaluate(
        setup_data=setup_db.data,
        context_data=context_data,
        db=db,
        now_nairobi=get_nairobi_time(),
        setup_packet_id=setup_db.id,
        config_override=policy_decision.policy_config,
        policy_hash=policy_decision.policy_hash
    )
    _guardrails_engine.persist(guardrails_result, db)

    setup_packet = TechnicalSetupPacket(**setup_db.data)
    risk_packet = RiskApprovalPacket(**risk_db.data)

    ticket = generate_order_ticket(setup_packet, risk_packet, db, guardrails=guardrails_result)
    ticket.setup_packet_id = setup_db.id
    ticket.risk_packet_id = risk_db.id
    db.commit()

    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                "http://localhost:8004/log/ticket",
                json=OrderTicketSchema.model_validate(ticket, from_attributes=True).model_dump(mode="json"),
                params={"setup_id": setup_db.id, "risk_decision_id": risk_db.id},
            )
    except Exception as e:
        logger.warning(f"Failed to log ticket to Journal: {e}")

    return ticket


@app.get("/guardrails/{setup_packet_id}")
async def get_guardrails(setup_packet_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Look up the most recent guardrails result for a setup packet."""
    from shared.database.models import GuardrailsLog
    record = db.query(GuardrailsLog).filter(
        GuardrailsLog.setup_packet_id == setup_packet_id
    ).order_by(GuardrailsLog.created_at.desc()).first()
    if not record:
        raise HTTPException(status_code=404, detail="No guardrails log found for this setup")
    return record.result_json


@app.post("/guardrails/evaluate")
async def evaluate_guardrails(
    pair: str, db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Evaluate guardrails for the latest setup of a pair without generating a ticket."""
    setup_db = db.query(Packet).filter(
        and_(
            Packet.packet_type == "TechnicalSetupPacket",
            Packet.data["asset_pair"].as_string() == pair,
        )
    ).order_by(Packet.created_at.desc()).first()
    if not setup_db:
        raise HTTPException(status_code=404, detail=f"No setup found for {pair}")

    ctx_db = db.query(Packet).filter(
        Packet.packet_type == "MarketContextPacket"
    ).order_by(Packet.created_at.desc()).first()
    context_data = ctx_db.data if ctx_db else {}

    result = _guardrails_engine.evaluate(
        setup_data=setup_db.data,
        context_data=context_data,
        db=db,
        now_nairobi=get_nairobi_time(),
        setup_packet_id=setup_db.id,
    )
    _guardrails_engine.persist(result, db)
    return result.model_dump(mode="json")


@app.get("/tickets/latest", response_model=OrderTicketSchema)
async def get_latest_ticket(pair: str, db: Session = Depends(get_db)):
    ticket = db.query(OrderTicket).filter(
        OrderTicket.pair == pair
    ).order_by(OrderTicket.created_at.desc()).first()
    if not ticket:
        raise HTTPException(status_code=404, detail=f"No tickets found for {pair}")
    return ticket


@app.get("/tickets", response_model=List[OrderTicketSchema])
async def list_tickets(
    date_str: Optional[str] = Query(None, alias="date"),
    db: Session = Depends(get_db),
):
    query = db.query(OrderTicket)
    if date_str:
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            query = query.filter(
                db.func.date(OrderTicket.created_at) == d
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Use YYYY-MM-DD")
    return query.order_by(OrderTicket.created_at.desc()).all()


@app.patch("/tickets/{ticket_id}/status", response_model=OrderTicketSchema)
async def update_ticket_status(ticket_id: str, status: str, db: Session = Depends(get_db)):
    """Manual status update: TAKEN / NOT_TAKEN / PENDING."""
    if status not in ("TAKEN", "NOT_TAKEN", "PENDING"):
        raise HTTPException(status_code=400, detail="Use TAKEN, NOT_TAKEN, or PENDING")
    ticket = db.query(OrderTicket).filter(
        OrderTicket.ticket_id == ticket_id
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    ticket.status = status
    db.commit()
    db.refresh(ticket)

    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                "http://localhost:8004/log/ticket",
                json=OrderTicketSchema.model_validate(ticket, from_attributes=True).model_dump(mode="json"),
            )
    except Exception as e:
        logger.warning(f"Failed to update ticket in Journal: {e}")

    return ticket
