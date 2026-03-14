import asyncio
import os
import time
from datetime import datetime, timezone
from datetime import time as dt_time
from typing import Any

import httpx
from sqlalchemy.orm import Session

import shared.database.session as db_session
from shared.database.models import (
    IncidentLog,
    JournalLog,
    LiveQuote,
    OrderTicket,
    Packet,
    SessionBriefing,
    TicketTradeLink,
    TradeFillLog,
)
from shared.database.models import (
    PositionSnapshot as PositionSnapshotModel,
)
from shared.logic.lockout_engine import LockoutEngine
from shared.logic.sessions import get_nairobi_time, get_session_label
from shared.types.trading import OrderTicketSchema

SERVICES = {
    "Ingestion": os.getenv("INGESTION_URL", "http://localhost:8001/health"),
    "Technical": os.getenv("TECHNICAL_URL", "http://localhost:8002/health"),
    "Risk": os.getenv("RISK_URL", "http://localhost:8003/health"),
    "Journal": os.getenv("JOURNAL_URL", "http://localhost:8004/health"),
    "Dashboard": os.getenv("DASHBOARD_URL", "http://localhost:8005/health"),
    "Orchestrator": os.getenv("ORCHESTRATOR_URL", "http://localhost:8006/health"),
    # Bridge is not included in the default compose stack.
    # Set BRIDGE_URL env var to enable health checking when bridge is running.
    "Bridge": os.getenv("BRIDGE_URL", ""),
}


async def get_service_health() -> dict[str, Any]:
    health_results = {}
    response_times = {}

    async with httpx.AsyncClient(timeout=1.0) as client:
        tasks = []
        for name, url in SERVICES.items():
            if not url:
                # Service not configured (e.g. bridge when BRIDGE_URL is unset)
                health_results[name] = "unconfigured"
                response_times[name] = 0
                continue
            tasks.append(check_health(client, name, url))

        results = await asyncio.gather(*tasks)
        for name, status, r_time in results:
            health_results[name] = status
            response_times[name] = r_time

    return health_results, response_times


async def check_health(client, name, url):
    start_time = time.time()
    try:
        response = await client.get(url)
        elapsed = int((time.time() - start_time) * 1000)
        if response.status_code == 200:
            return name, "healthy", elapsed
        return name, "unhealthy", elapsed
    except Exception:
        elapsed = int((time.time() - start_time) * 1000)
        return name, "unhealthy", elapsed


def get_dashboard_data(db: Session, asset_pairs: list[str] = ["XAUUSD", "GBPJPY"]):
    # Nairobi Time
    now_nairobi = get_nairobi_time()
    now_utc = datetime.now(timezone.utc)

    # 1. PERMISSION STATE PANEL
    # In a real scenario, these would come from a real sync with Risk/MT5.
    # For the HUD, we'll pull latest logs or static defaults if missing.
    lockout_config = {
        "max_daily_loss_pct": 2.0,
        "max_consecutive_losses": 3,
        "account_balance": 100000.0,  # Standard pilot balance
    }
    # Mocking account state for now - in production, this pulls from a dedicated AccountState table/service
    account_state = {
        "daily_loss": 0.0,
        "consecutive_losses": 0,
        "account_balance": 100000.0,
    }

    lockout_engine = LockoutEngine(lockout_config)
    permission_state, permission_msg = lockout_engine.evaluate(account_state, db=db)

    # 2. SESSION STATE PANEL
    # Compute session for a primary pair or return a map
    primary_pair = asset_pairs[0]
    session_label = get_session_label(now_nairobi, primary_pair)

    # Simple countdown to next boundary
    current_time = now_nairobi.time()
    boundaries = [
        (
            dt_time(3, 0),
            "ASIA_SESSION" if primary_pair == "GBPJPY" else "OUT_OF_SESSION",
        ),
        (dt_time(7, 0), "PRE_SESSION"),
        (dt_time(11, 0), "LONDON_OPEN"),
        (dt_time(14, 0), "LONDON_MID"),
        (dt_time(16, 0), "NY_OPEN"),
        (dt_time(19, 0), "POST_SESSION"),
        (dt_time(22, 0), "OUT_OF_SESSION"),
    ]
    next_boundary = None
    for b_time, b_label in boundaries:
        if b_time > current_time:
            next_boundary = b_time
            break
    if not next_boundary:
        next_boundary = boundaries[0][0]  # Next day Asia

    # Calculate minutes until next boundary
    today = now_nairobi.date()
    boundary_dt = datetime.combine(today, next_boundary)
    if next_boundary <= current_time:
        from datetime import timedelta

        boundary_dt += timedelta(days=1)

    time_to_transition = int(
        (boundary_dt.replace(tzinfo=now_nairobi.tzinfo) - now_nairobi).total_seconds()
        / 60
    )

    # 3. BIAS STATE PANEL (Per Pair)
    bias_states = {}
    for pair in asset_pairs:
        p_fund = (
            db.query(Packet)
            .filter(
                Packet.packet_type == "PairFundamentalsPacket",
                Packet.data["asset_pair"].as_string() == pair,
            )
            .order_by(Packet.created_at.desc())
            .first()
        )

        if p_fund:
            bias_states[pair] = {
                "bias": p_fund.data.get("bias"),
                "is_invalidated": p_fund.data.get("is_invalidated", False),
                "age_m": int(
                    (
                        now_utc - p_fund.created_at.replace(tzinfo=timezone.utc)
                    ).total_seconds()
                    / 60
                ),
            }
        else:
            bias_states[pair] = {"bias": "NEUTRAL", "is_invalidated": False, "age_m": 0}

    # 4. SETUP PROGRESSION PANEL
    setup_packets = (
        db.query(Packet)
        .filter(Packet.packet_type == "TechnicalSetupPacket")
        .order_by(Packet.created_at.desc())
        .limit(10)
        .all()
    )
    latest_setups = []
    for p in setup_packets:
        is_fresh = (
            now_utc - p.created_at.replace(tzinfo=timezone.utc)
        ).total_seconds() < 60
        latest_setups.append(
            {
                "asset_pair": p.data.get("asset_pair"),
                "stage": p.data.get("stage"),
                "is_aligned": p.data.get(
                    "is_aligned", False
                ),  # Refactored from 'score'
                "is_fresh": is_fresh,
                "age_str": f"{int((now_utc - p.created_at.replace(tzinfo=timezone.utc)).total_seconds())}s",
            }
        )

    # 5. RISK BUDGET PANEL
    risk_budget = {
        "daily_loss_pct": account_state["daily_loss"]
        / account_state["account_balance"]
        * 100,
        "max_daily_loss_pct": lockout_config["max_daily_loss_pct"],
        "consecutive_losses": account_state["consecutive_losses"],
        "max_consecutive_losses": lockout_config["max_consecutive_losses"],
    }

    # 6. ACTIVE POSITIONS PANEL
    live_positions = db.query(
        PositionSnapshotModel
    ).all()  # Already imported in main.py but needs to be here
    # We will pass raw models and format in template

    # 7. NOTICE / REVIEW LOG
    latest_incidents = (
        db.query(IncidentLog).order_by(IncidentLog.created_at.desc()).limit(10).all()
    )

    # Bridge Data for the bottom strip
    live_quotes = (
        db.query(LiveQuote).order_by(LiveQuote.captured_at.desc()).limit(5).all()
    )

    return {
        "permission_state": permission_state.value,
        "permission_msg": permission_msg,
        "session_label": session_label,
        "time_to_transition": time_to_transition,
        "bias_states": bias_states,
        "latest_setups": latest_setups,
        "risk_budget": risk_budget,
        "live_positions": live_positions,
        "latest_incidents": latest_incidents,
        "live_quotes": live_quotes,
        "now_nairobi_str": now_nairobi.strftime("%H:%M:%S"),
    }


async def get_tickets(pair: str | None = None) -> list[OrderTicketSchema]:
    """Fetches order tickets, optionally filtered by pair."""
    db = db_session.SessionLocal()
    try:
        query = db.query(OrderTicket)
        if pair:
            query = query.filter(OrderTicket.pair == pair)

        tickets = query.order_by(OrderTicket.created_at.desc()).limit(50).all()

        # Convert to schemas with formatters
        ticket_schemas = [
            OrderTicketSchema.model_validate(t, from_attributes=True) for t in tickets
        ]

        # Enrich with bridge and journal data
        for t_schema in ticket_schemas:
            link = (
                db.query(TicketTradeLink)
                .filter(TicketTradeLink.ticket_id == t_schema.ticket_id)
                .first()
            )
            if link:
                t_schema.broker_trade_id = link.broker_trade_id
                # Get execution timestamp from the fill log
                fill = (
                    db.query(TradeFillLog)
                    .filter(
                        TradeFillLog.broker_trade_id == link.broker_trade_id,
                        TradeFillLog.event_type == "OPEN",
                    )
                    .first()
                )
                if fill:
                    t_schema.executed_at = fill.time_eat

                # Get realized PnL/R from the most recent journal entry for this ticket
                journal = (
                    db.query(JournalLog)
                    .filter(
                        JournalLog.ticket_id == t_schema.ticket_id,
                        JournalLog.event_type.in_(["TRADE_CLOSED", "PARTIAL_CLOSE"]),
                    )
                    .order_by(JournalLog.created_at.desc())
                    .first()
                )
                if journal:
                    t_schema.realized_r = (
                        journal.data.get("realized_r") if journal.data else None
                    )

        return ticket_schemas
    finally:
        db.close()


def get_briefings(db: Session, limit: int = 30) -> list[dict[str, Any]]:
    """Return briefing metadata for the list view."""
    records = (
        db.query(SessionBriefing)
        .order_by(SessionBriefing.created_at.desc())
        .limit(limit)
        .all()
    )
    return records


def get_latest_briefing(db: Session) -> dict[str, Any] | None:
    """Return the most recent briefing record, or None."""
    return db.query(SessionBriefing).order_by(SessionBriefing.created_at.desc()).first()
