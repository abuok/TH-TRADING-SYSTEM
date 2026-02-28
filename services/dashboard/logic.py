import os
import asyncio
import httpx
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text, desc

import shared.database.session as db_session
from shared.database.models import Packet, KillSwitch, IncidentLog, OrderTicket, SessionBriefing, LiveQuote, SymbolSpec
from shared.logic.sessions import get_nairobi_time, get_session_label
from shared.types.trading import OrderTicketSchema

SERVICES = {
    "Ingestion": os.getenv("INGESTION_URL", "http://localhost:8001/health"),
    "Technical": os.getenv("TECHNICAL_URL", "http://localhost:8002/health"),
    "Risk": os.getenv("RISK_URL", "http://localhost:8003/health"),
    "Journal": os.getenv("JOURNAL_URL", "http://localhost:8004/health"),
    "Orchestrator": os.getenv("ORCHESTRATOR_URL", "http://localhost:8000/health"),
    "Bridge": os.getenv("BRIDGE_URL", "http://localhost:8005/health")
}

async def get_service_health() -> Dict[str, Any]:
    health_results = {}
    response_times = {}
    
    async with httpx.AsyncClient(timeout=1.0) as client:
        tasks = []
        for name, url in SERVICES.items():
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

def get_dashboard_data(db: Session):
    # Nairobi Time
    now_nairobi = get_nairobi_time()
    
    # 1. Kill Switches
    kill_switches = db.query(KillSwitch).filter(KillSwitch.is_active == 1).all()
    
    # 2. Latest Market Context (for events and session)
    latest_context = db.query(Packet).filter(Packet.packet_type == "MarketContextPacket").order_by(Packet.created_at.desc()).first()
    
    events = []
    no_trade_windows = []
    if latest_context and "high_impact_events" in latest_context.data:
        events = latest_context.data.get("high_impact_events", [])[:5]
        no_trade_windows = latest_context.data.get("no_trade_windows", [])
    
    # 3. Latest 10 Setups
    setup_packets = db.query(Packet).filter(Packet.packet_type == "TechnicalSetupPacket").order_by(Packet.created_at.desc()).limit(10).all()
    latest_setups = []
    for p in setup_packets:
        # Check freshness (TTL 60s for setups)
        is_fresh = (datetime.now(timezone.utc) - p.created_at.replace(tzinfo=timezone.utc)).total_seconds() < 60
        latest_setups.append({
            "asset_pair": p.data.get("asset_pair"),
            "stage": p.data.get("stage"),
            "score": p.data.get("score"),
            "is_fresh": is_fresh
        })
        
    # 4. Latest 10 Risk Decisions
    decision_packets = db.query(Packet).filter(Packet.packet_type == "RiskApprovalPacket").order_by(Packet.created_at.desc()).limit(10).all()
    latest_decisions = []
    for p in decision_packets:
        latest_decisions.append({
            "asset_pair": p.data.get("asset_pair"),
            "action": p.data.get("action"),
            "reason": p.data.get("reason")
        })
        
    # 5. Latest 10 Incidents
    latest_incidents = db.query(IncidentLog).order_by(IncidentLog.created_at.desc()).limit(10).all()
    
    # 6. Live Bridge Data
    live_quotes = db.query(LiveQuote).order_by(LiveQuote.captured_at.desc()).limit(5).all()
    symbol_specs = db.query(SymbolSpec).order_by(SymbolSpec.captured_at.desc()).limit(5).all()

    return {
        "now_nairobi_str": now_nairobi.strftime("%Y-%m-%d %H:%M:%S"),
        "session_label": get_session_label(now_nairobi),
        "kill_switches": kill_switches,
        "events": events,
        "no_trade_windows": no_trade_windows,
        "latest_setups": latest_setups,
        "latest_decisions": latest_decisions,
        "latest_incidents": latest_incidents,
        "live_quotes": live_quotes,
        "symbol_specs": symbol_specs
    }

async def get_tickets(pair: Optional[str] = None) -> List[OrderTicketSchema]:
    """Fetches order tickets, optionally filtered by pair."""
    db = db_session.SessionLocal()
    try:
        query = db.query(OrderTicket)
        if pair:
            query = query.filter(OrderTicket.pair == pair)
        
        tickets = query.order_by(OrderTicket.created_at.desc()).limit(50).all()
        
        # Convert to schemas with formatters
        return [OrderTicketSchema.model_validate(t, from_attributes=True) for t in tickets]
    finally:
        db.close()


def get_briefings(db: Session, limit: int = 30) -> List[Dict[str, Any]]:
    """Return briefing metadata for the list view."""
    records = db.query(SessionBriefing).order_by(
        SessionBriefing.created_at.desc()
    ).limit(limit).all()
    return records


def get_latest_briefing(db: Session) -> Optional[Dict[str, Any]]:
    """Return the most recent briefing record, or None."""
    return db.query(SessionBriefing).order_by(
        SessionBriefing.created_at.desc()
    ).first()
