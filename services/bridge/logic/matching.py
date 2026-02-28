import re
from datetime import timedelta
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_

from shared.database.models import OrderTicket, ExecutionPrepLog
from shared.types.trade_capture import TradeFillEvent

def match_fill_to_ticket(db: Session, fill: TradeFillEvent) -> Tuple[Optional[str], str, float]:
    """
    Attempts to match a trade fill to a ticket.
    Returns: (ticket_id, method, confidence)
    """
    
    # 1. Deterministic Match: Comment parsing
    if fill.comment:
        # Expected format: TICKET:<ticket_id>|PREP:<prep_id>|POLICY:<policy>
        match = re.search(r"TICKET:([A-Za-z0-9_-]+)", fill.comment)
        if match:
            ticket_id = match.group(1)
            # Verify ticket exists
            ticket = db.query(OrderTicket).filter(OrderTicket.ticket_id == ticket_id).first()
            if ticket:
                return ticket_id, "COMMENT", 1.0

    # 2. Heuristic Match: Fallback
    # Criteria:
    # - Same symbol
    # - Same side (BUY/SELL)
    # - Time within 5m of ExecutionPrep creation
    # - Price within tolerance (e.g. 10 pips/ticks)
    
    # First, find related prep logs for the symbol and time window
    window_start = fill.time_utc - timedelta(minutes=5)
    window_end = fill.time_utc + timedelta(minutes=5)
    
    possible_preps = db.query(ExecutionPrepLog).filter(
        and_(
            ExecutionPrepLog.created_at >= window_start,
            ExecutionPrepLog.created_at <= window_end,
            ExecutionPrepLog.status == "ACTIVE"
        )
    ).all()
    
    best_match = None
    best_confidence = 0.0
    
    for prep in possible_preps:
        ticket = prep.ticket
        if not ticket:
            continue
            
        # Basic constraints
        if ticket.pair != fill.symbol:
            continue
        if ticket.direction != fill.side:
            continue
            
        # Price tolerance check
        # For simplicity, we use a percentage-based tolerance if we don't have tick size here
        # but let's assume 0.1% tolerance for now as a heuristic
        price_diff = abs(ticket.entry_price - fill.price)
        price_tolerance = ticket.entry_price * 0.001 # 0.1%
        
        if price_diff <= price_tolerance:
            # Match found
            confidence = 0.8 # Lower confidence for heuristic
            if best_match is None or confidence > best_confidence:
                best_match = ticket.ticket_id
                best_confidence = confidence
                
    if best_match:
        return best_match, "HEURISTIC", best_confidence

    return None, "NONE", 0.0
