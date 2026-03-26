"""
shared/database/optimizations.py

Database optimization utilities and index recommendations for the TH Trading System.
This module documents necessary indexes for high-performance querying and provides
helpers for common bulk operations.
"""

# ── Index Recommendations for Alembic Migrations ────────────────
# Copy-paste these into an Alembic migration to improve query performance.

"""
1. Packets - Latest by Type & Pair
   CREATE INDEX ix_packets_type_pair_created ON packets (
       packet_type, 
       (data->>'asset_pair'), 
       created_at DESC
   );

2. Order Tickets - Dashboard Filter
   CREATE INDEX ix_order_tickets_pair_created ON order_tickets (
       pair, 
       created_at DESC
   );

3. Trade Fills - Broker Lookup
   CREATE INDEX ix_trade_fills_broker_event ON trade_fills_log (
       broker_trade_id, 
       event_type
   );

4. Alignment Logs - Quality History
   CREATE INDEX ix_alignment_logs_pair_created ON alignment_logs (
       pair, 
       created_at DESC
   );

5. Journal Logs - Ticket Timeline
   CREATE INDEX ix_journal_logs_ticket_event ON journal_logs (
       ticket_id, 
       event_type
   );
"""

from typing import Any, Iterable, TypeVar
from sqlalchemy.orm import Session, joinedload
from shared.database.models import Packet

T = TypeVar("T")

def bulk_fetch_latest_packets(db: Session, packet_types: Iterable[str], pairs: Iterable[str] = None) -> dict[str, Any]:
    """
    Fetches the latest packets for a set of types and optionally pairs in a bulk-safe manner.
    Reduces N+1 overhead for dashboard and Jarvis intelligence engines.
    """
    query = db.query(Packet).filter(Packet.packet_type.in_(packet_types))
    
    # We fetch a reasonably sized batch and filter for newest in-memory to avoid 
    # complex DISTINCT ON / Window function syntax which varies by DB driver (SQLite vs PG).
    # 20 packets is usually enough for the latest state of 2-4 pairs.
    recent_packets = query.order_by(Packet.created_at.desc()).limit(30).all()
    
    results = {}
    for p_type in packet_types:
        if pairs:
            for pair in pairs:
                # Key format: "PacketType:PAIR"
                match = next((p for p in recent_packets if p.packet_type == p_type and p.data.get("asset_pair") == pair), None)
                results[f"{p_type}:{pair}"] = match
        else:
            match = next((p for p in recent_packets if p.packet_type == p_type), None)
            results[p_type] = match
            
    return results
