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
from shared.logic.caching import cached_data
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


async def get_service_health() -> tuple[dict[str, str], dict[str, int]]:
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


@cached_data("dashboard_account_state", ttl_seconds=60)
def get_cached_account_state() -> dict:
    """Mock account state. Cached for 1 min in Redis."""
    return {
        "daily_loss": 0.0,
        "consecutive_losses": 0,
        "account_balance": 100000.0,
    }


@cached_data("dashboard_market_context", ttl_seconds=300)
def get_cached_market_context() -> dict:
    """Mock market context. Cached for 5 min in Redis."""
    return {
        "volatility": "MODERATE",
        "trend": "BULLISH",
    }


def get_dashboard_data(db: Session, asset_pairs: list[str] | None = None):
    # Nairobi Time
    if asset_pairs is None:
        asset_pairs = ["XAUUSD", "GBPJPY"]
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
    account_state = get_cached_account_state()
    market_context = get_cached_market_context()

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
    for b_time, _b_label in boundaries:
        if b_time > current_time:
            next_boundary = b_time
            break
    if not next_boundary:
        next_boundary = boundaries[0][0]  # Next day Asia

    # Calculate minutes until next boundary
    today = now_nairobi.date()
    assert next_boundary is not None  # guaranteed: fallback on line 127 always sets it
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

    # 8. JARVIS INTELLIGENCE MODEL
    # Synthesize the raw states into the decision engine model
    jarvis_status = "NO TRADE"
    jarvis_reasoning = "System is IDLE. No setup forming."
    jarvis_stage = "IDLE"
    jarvis_aligned = False
    
    # Analyze the most recent setup packet
    if setup_packets:
        latest = setup_packets[0]
        jarvis_stage = latest.data.get("stage", "IDLE")
        jarvis_aligned = latest.data.get("is_aligned", False)
        
        # Extract reasons if they exist
        reasons = latest.data.get("reason_codes", [])
        last_reason = reasons[-1] if reasons else None
        
        if permission_state.value == "HARD_LOCK":
            jarvis_reasoning = f"Execution physically sealed. {permission_msg}"
        elif session_label == "OUT_OF_SESSION":
            jarvis_reasoning = "No trade. System frozen outside of allowed sessions."
        elif jarvis_stage == "TRIGGER" and jarvis_aligned:
            jarvis_status = "VALID TRADE"
            jarvis_reasoning = "All conditions met. Setup aligned and triggered."
        elif jarvis_stage == "TRIGGER" and not jarvis_aligned:
            jarvis_reasoning = "Trade triggered but blocked by alignment guardrails."
        elif jarvis_stage in ["BIAS", "SWEEP", "DISPLACE"]:
            jarvis_reasoning = last_reason or f"Valid setup forming. Currently at {jarvis_stage} stage."
        elif jarvis_stage == "RETEST":
            jarvis_reasoning = last_reason or "Displacement confirmed. Awaiting retest/trigger."
        elif jarvis_stage == "CHOCH_BOS":
            jarvis_reasoning = last_reason or "Structure shift confirmed. Monitoring for retest."
            
    # Create the unified thought stream (combining setups and incidents)
    thought_stream = []
    
    for inc in reversed(latest_incidents[:5]):
        thought_stream.append({
            "time": inc.created_at.strftime("%H:%M:%S"),
            "msg": f"[{inc.component}] {inc.message}",
            "type": "incident"
        })
        
    for p in reversed(setup_packets[:3]):
        reasons = p.data.get("reason_codes", [])
        stage = p.data.get("stage", "UNKNOWN")
        if reasons:
            thought_stream.append({
                "time": p.created_at.strftime("%H:%M:%S"),
                "msg": f"[{stage}] {reasons[-1]}",
                "type": "event"
            })
            
    # Sort chronological
    thought_stream = sorted(thought_stream, key=lambda x: x["time"], reverse=True)

    jarvis_model = {
        "status": jarvis_status,
        "reasoning": jarvis_reasoning,
        "stage": jarvis_stage,
        "is_aligned": jarvis_aligned,
        "thought_stream": thought_stream[:8]
    }

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
        "jarvis_model": jarvis_model,
    }


async def get_tickets(pair: str | None = None) -> list[OrderTicketSchema]:
    """Fetches order tickets, optimized for performance via joins and bulk loading."""
    from sqlalchemy.orm import joinedload
    db = db_session.SessionLocal()
    try:
        query = db.query(OrderTicket).options(
            joinedload(OrderTicket.trade_links),
            joinedload(OrderTicket.journal_entries)
        )
        if pair:
            query = query.filter(OrderTicket.pair == pair)

        tickets = query.order_by(OrderTicket.created_at.desc()).limit(50).all()

        # Collect all broker_trade_ids for a single bulk fetch of TradeFillLogs
        broker_trade_ids = []
        for t in tickets:
            for link in t.trade_links:
                broker_trade_ids.append(link.broker_trade_id)

        fill_map = {}
        if broker_trade_ids:
            fills = (
                db.query(TradeFillLog)
                .filter(
                    TradeFillLog.broker_trade_id.in_(broker_trade_ids),
                    TradeFillLog.event_type == "OPEN"
                )
                .all()
            )
            # Map by broker_trade_id for O(1) lookup
            fill_map = {f.broker_trade_id: f for f in fills}

        ticket_schemas = []
        for t in tickets:
            t_schema = OrderTicketSchema.model_validate(t, from_attributes=True)
            
            # Enrich with trade links (already loaded)
            if t.trade_links:
                link = t.trade_links[0]  # Take primary link
                t_schema.broker_trade_id = link.broker_trade_id
                
                # Enrich with fill data from pre-fetched map
                fill = fill_map.get(link.broker_trade_id)
                if fill:
                    t_schema.executed_at = fill.time_eat

            # Enrich with realized R from journal entries (already loaded)
            if t.journal_entries:
                # Find the most recent exit-related entry
                exit_entries = [
                    j for j in t.journal_entries 
                    if j.event_type in ("TRADE_CLOSED", "PARTIAL_CLOSE")
                ]
                if exit_entries:
                    # Sorted by created_at desc (journals are usually appended)
                    latest_exit = sorted(exit_entries, key=lambda x: x.created_at, reverse=True)[0]
                    t_schema.realized_r = (
                        latest_exit.data.get("realized_r") if latest_exit.data else None
                    )

            ticket_schemas.append(t_schema)

        return ticket_schemas
    finally:
        db.close()


def get_jarvis_data(db: Session) -> dict[str, Any]:
    """
    Standalone function to generate the JARVIS intelligence model JSON.
    Powers the /api/jarvis endpoint for live frontend polling.
    Returns a fully JSON-serializable dict.
    """
    now_nairobi = get_nairobi_time()
    now_utc = datetime.now(timezone.utc)

    # ── Permission & Lockout State ──────────────────────────────
    lockout_config = {
        "max_daily_loss_pct": 2.0,
        "max_consecutive_losses": 3,
        "account_balance": 100000.0,
    }
    account_state = get_cached_account_state()
    market_context = get_cached_market_context()
    
    lockout_engine = LockoutEngine(lockout_config)
    permission_state_enum, permission_msg = lockout_engine.evaluate(account_state, db=db)
    permission_state = permission_state_enum.value

    # ── Session ─────────────────────────────────────────────────
    pairs = ["XAUUSD", "GBPJPY"]
    session_label = get_session_label(now_nairobi, pairs[0])

    # ── Bias States (Bulk optimized) ──────────────────────────────
    bias_states: dict[str, Any] = {}
    from sqlalchemy import func
    
    # Fetch latest bias packets for the target pairs
    # Note: We fetch a small batch to ensure we get the latest for each pair in the set
    recent_bias_packets = (
        db.query(Packet)
        .filter(Packet.packet_type == "PairFundamentalsPacket")
        .order_by(Packet.created_at.desc())
        .limit(20)
        .all()
    )
    
    for pair in pairs:
        p_fund = next((p for p in recent_bias_packets if p.data.get("asset_pair") == pair), None)
        if p_fund:
            bias_states[pair] = {
                "bias": p_fund.data.get("bias_label", "NEUTRAL"),
                "bias_score": p_fund.data.get("bias_score", 0.0),
                "is_invalidated": p_fund.data.get("is_invalidated", False),
                "age_m": int(
                    (now_utc - p_fund.created_at.replace(tzinfo=timezone.utc)).total_seconds() / 60
                ),
                "created_at": p_fund.created_at.strftime("%H:%M:%S"),
            }
        else:
            bias_states[pair] = {
                "bias": "NEUTRAL",
                "bias_score": 0.0,
                "is_invalidated": False,
                "age_m": 0,
                "created_at": None,
            }

    # ── Setup Packets (PHX state) ────────────────────────────────
    setup_packets = (
        db.query(Packet)
        .filter(Packet.packet_type == "TechnicalSetupPacket")
        .order_by(Packet.created_at.desc())
        .limit(15)
        .all()
    )

    # ── Alignment Logs (Bulk optimized) ───────────────────────────
    from shared.database.models import AlignmentLog
    alignment_data: dict[str, Any] = {}
    
    recent_alignments = (
        db.query(AlignmentLog)
        .filter(AlignmentLog.pair.in_(pairs))
        .order_by(AlignmentLog.created_at.desc())
        .limit(10)
        .all()
    )
    
    for pair in pairs:
        alog = next((a for a in recent_alignments if a.pair == pair), None)
        if alog:
            raw = alog.result_json or {}
            checks = {k: bool(v) for k, v in raw.items() if isinstance(v, (bool, int))}
            alignment_data[pair] = {
                "is_aligned": alog.is_aligned,
                "checks": checks,
                "reason_codes": alog.reason_codes or [],
                "age_m": int(
                    (now_utc - alog.created_at.replace(tzinfo=timezone.utc)).total_seconds() / 60
                ),
            }
        else:
            alignment_data[pair] = {
                "is_aligned": False,
                "checks": {},
                "reason_codes": ["No alignment data available"],
                "age_m": 0,
            }

    # ── Latest Setups (per pair) ──────────────────────────────────
    latest_setups: list[dict] = []
    for p in setup_packets:
        age_s = int((now_utc - p.created_at.replace(tzinfo=timezone.utc)).total_seconds())
        latest_setups.append({
            "asset_pair": p.data.get("asset_pair"),
            "stage": p.data.get("stage", "IDLE"),
            "is_aligned": p.data.get("is_aligned", False),
            "reason_codes": p.data.get("reason_codes", []),
            "age_s": age_s,
            "age_str": f"{age_s}s" if age_s < 60 else f"{age_s // 60}m",
            "is_fresh": age_s < 90,
            "created_at": p.created_at.strftime("%H:%M:%S"),
        })

    # ── Incidents / Thought Stream ────────────────────────────────
    latest_incidents = (
        db.query(IncidentLog).order_by(IncidentLog.created_at.desc()).limit(15).all()
    )

    thought_stream: list[dict] = []
    for inc in latest_incidents:
        thought_stream.append({
            "time": inc.created_at.strftime("%H:%M"),
            "msg": f"{inc.message}",
            "type": "incident",
            "severity": inc.severity,
        })
    for p in setup_packets[:5]:
        reasons = p.data.get("reason_codes", [])
        stage = p.data.get("stage", "UNKNOWN")
        pair = p.data.get("asset_pair", "?")
        for r in reasons[-2:]:
            thought_stream.append({
                "time": p.created_at.strftime("%H:%M"),
                "msg": f"[{pair}:{stage}] {r}",
                "type": "setup",
                "severity": "INFO",
            })
    thought_stream = sorted(thought_stream, key=lambda x: x["time"], reverse=True)[:18]

    # ── Risk Budget ───────────────────────────────────────────────
    daily_loss_pct = account_state["daily_loss"] / account_state["account_balance"] * 100
    risk_budget = {
        "daily_loss_pct": round(daily_loss_pct, 3),
        "max_daily_loss_pct": lockout_config["max_daily_loss_pct"],
        "daily_loss_pct_used": round(daily_loss_pct / lockout_config["max_daily_loss_pct"] * 100, 1),
        "consecutive_losses": account_state["consecutive_losses"],
        "max_consecutive_losses": lockout_config["max_consecutive_losses"],
    }

    # ── JARVIS INTELLIGENCE ENGINE ────────────────────────────────
    # Determine the primary active setup (most recent, most advanced stage)
    STAGE_RANK = {
        "TRIGGER": 7, "RETEST": 6, "CHOCH_BOS": 5,
        "DISPLACE": 4, "SWEEP": 3, "BIAS": 2, "IDLE": 1,
    }

    primary_pair = "XAUUSD"
    primary_stage = "IDLE"
    primary_aligned = False
    primary_reasons: list[str] = []
    primary_setup = None

    for s in latest_setups:
        rank = STAGE_RANK.get(str(s["stage"]).upper(), 0)
        p_rank = STAGE_RANK.get(primary_stage.upper(), 0)
        if rank > p_rank:
            primary_stage = str(s["stage"]).upper()
            primary_pair = str(s["asset_pair"] or "XAUUSD")
            primary_aligned = bool(s["is_aligned"])
            primary_reasons = list(s["reason_codes"])
            primary_setup = s

    # Generate authoritative Jarvis reasoning
    def _build_reasoning(stage: str, aligned: bool, reasons: list, perm: str, session: str) -> tuple[str, str]:
        """Returns (status_text, reasoning_text) pair."""
        if perm == "HARD_LOCK":
            return "NO TRADE", "Execution sealed. System-level intervention active. No entries permitted."

        if session == "OUT_OF_SESSION":
            return "NO TRADE", "Market closed for this strategy. Waiting for London or New York open."

        if stage == "IDLE":
            return "MONITORING", "No setup forming. System is scanning for liquidity sweep opportunity."

        if stage == "BIAS":
            bias = bias_states.get(primary_pair, {}).get("bias", "NEUTRAL")
            return "MONITORING", f"Directional bias established: {bias}. Watching for sell-side / buy-side sweep to form."

        if stage == "SWEEP":
            return "MONITORING", "Liquidity has been swept. Monitoring for strong displacement candle to confirm intent."

        if stage == "DISPLACE":
            return "MONITORING", "Displacement confirmed. Waiting for structure shift (BOS/CHOCH) to validate the move."

        if stage == "CHOCH_BOS":
            return "ALERT", "Structure shift confirmed. Market has broken internal structure. Monitoring for retest of the level."

        if stage == "RETEST":
            return "ALERT", "Price retesting the broken structure level. Entry trigger imminent. Prepare to act."

        if stage == "TRIGGER" and aligned:
            return "VALID TRADE", "All conditions satisfied. Setup is triggered and fully aligned. Awaiting manual review."

        if stage == "TRIGGER" and not aligned:
            failed = [r.replace("FAILED: ", "") for r in reasons if "FAILED" in r]
            if failed:
                failed_str = " | ".join(failed)
                return "BLOCKED", f"Setup triggered but blocked by alignment. Failed: {failed_str}."
            return "BLOCKED", "Setup triggered but one or more alignment checks failed. Review guardrails."

        return "MONITORING", f"System at {stage} stage. Continuing evaluation."

    jarvis_status, jarvis_reasoning = _build_reasoning(
        primary_stage, primary_aligned, primary_reasons, permission_state, session_label
    )

    # ── Live Quotes ───────────────────────────────────────────────
    live_quotes = []
    try:
        from shared.database.models import LiveQuote
        raw_quotes = db.query(LiveQuote).order_by(LiveQuote.captured_at.desc()).limit(4).all()
        for q in raw_quotes:
            live_quotes.append({
                "symbol": q.symbol,
                "bid": q.bid,
                "ask": q.ask,
                "spread": round((q.ask - q.bid) * 10000, 1) if q.ask and q.bid else None,
                "age_s": int((now_utc - q.captured_at.replace(tzinfo=timezone.utc)).total_seconds()),
            })
    except Exception:
        pass

    return {
        "ts": now_nairobi.strftime("%H:%M:%S"),
        "permission_state": permission_state,
        "permission_msg": permission_msg,
        "session_label": session_label,
        "bias_states": bias_states,
        "alignment_data": alignment_data,
        "latest_setups": latest_setups,
        "primary_pair": primary_pair,
        "primary_stage": primary_stage,
        "risk_budget": risk_budget,
        "thought_stream": thought_stream,
        "live_quotes": live_quotes,
        "jarvis": {
            "status": jarvis_status,
            "reasoning": jarvis_reasoning,
            "stage": primary_stage,
            "pair": primary_pair,
            "is_aligned": primary_aligned,
        },
    }


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
