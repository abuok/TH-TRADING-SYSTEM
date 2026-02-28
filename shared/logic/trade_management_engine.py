import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict
from sqlalchemy.orm import Session

from shared.database.models import OrderTicket, PositionSnapshot, TicketTradeLink, ManagementSuggestionLog, LiveQuote
from shared.types.trade_management import PositionManagementSuggestion, SuggestionType
from shared.providers.price_quote import PriceQuoteProvider, get_price_quote_provider
from shared.logic.sessions import get_nairobi_time

logger = logging.getLogger("TradeManagementEngine")

def calculate_r_multiple(side: str, entry_price: float, sl: float, current_price: float) -> float:
    """Calculate the current R multiple (Risk/Reward ratio progress)."""
    risk = abs(entry_price - sl)
    if risk == 0:
        return 0.0
    
    if side.upper() == "BUY":
        profit = current_price - entry_price
    else:
        profit = entry_price - current_price
        
    return profit / risk

def generate_suggestions_for_position(
    db: Session,
    snapshot: PositionSnapshot,
    quote_provider: PriceQuoteProvider,
    now_eat: datetime
) -> List[PositionManagementSuggestion]:
    """Generate rule-based suggestions for a single position snapshot."""
    # 1. Find the linked ticket
    link = db.query(TicketTradeLink).filter(TicketTradeLink.broker_trade_id == snapshot.position_id).first()
    if not link:
        return []
    
    ticket = db.query(OrderTicket).filter(OrderTicket.ticket_id == link.ticket_id).first()
    if not ticket:
        return []
    
    # 2. Get current quote
    quote = quote_provider.get_quote(snapshot.symbol)
    if not quote:
        logger.warning(f"No quote available for {snapshot.symbol}")
        return []
    
    current_price = quote.bid if snapshot.side == "BUY" else quote.ask
    current_r = calculate_r_multiple(snapshot.side, snapshot.avg_price, snapshot.sl, current_price)
    
    suggestions = []
    
    # Rule: Move SL to BE at 1.0R
    if current_r >= 1.0:
        # Check if SL is already at or better than BE
        is_already_be = False
        if snapshot.side == "BUY":
            is_already_be = snapshot.sl >= (snapshot.avg_price - 0.00001) # Small epsilon
        else:
            is_already_be = snapshot.sl <= (snapshot.avg_price + 0.00001)
            
        if not is_already_be:
            suggestions.append(PositionManagementSuggestion(
                created_at_eat=now_eat,
                ticket_id=ticket.id, 
                broker_trade_id=snapshot.position_id,
                symbol=snapshot.symbol,
                side=snapshot.side,
                lots=snapshot.lots,
                entry_price=snapshot.avg_price,
                sl=snapshot.sl,
                tp1=ticket.take_profit_1,
                tp2=ticket.take_profit_2,
                current_price=current_price,
                current_r=current_r,
                suggestion_type=SuggestionType.MOVE_SL_TO_BE,
                severity="WARN",
                reasons=[f"Price reached {current_r:.2f}R (Reward threshold: 1.0R)"],
                expires_at_eat=now_eat + timedelta(minutes=15),
                instruction=f"Move SL to Entry: {snapshot.avg_price:.5f}"
            ))

    # Rule: Partial TP1
    if ticket.take_profit_1:
        hit_tp1 = False
        if snapshot.side == "BUY":
            hit_tp1 = current_price >= ticket.take_profit_1
        else:
            hit_tp1 = current_price <= ticket.take_profit_1
            
        if hit_tp1:
            suggestions.append(PositionManagementSuggestion(
                created_at_eat=now_eat,
                ticket_id=ticket.id,
                broker_trade_id=snapshot.position_id,
                symbol=snapshot.symbol,
                side=snapshot.side,
                lots=snapshot.lots,
                entry_price=snapshot.avg_price,
                sl=snapshot.sl,
                tp1=ticket.take_profit_1,
                tp2=ticket.take_profit_2,
                current_price=current_price,
                current_r=current_r,
                suggestion_type=SuggestionType.TAKE_PARTIAL_TP1,
                severity="CRITICAL",
                reasons=[f"Price hit TP1: {ticket.take_profit_1:.5f}"],
                expires_at_eat=now_eat + timedelta(minutes=15),
                instruction=f"Take Partial Profit TP1 at {ticket.take_profit_1:.5f}"
            ))

    return suggestions

def run_management_cycle(db: Session):
    """Run the full management cycle for all open positions."""
    now_eat = get_nairobi_time()
    quote_provider = get_price_quote_provider()
    
    # Get all active snapshots
    snapshots = db.query(PositionSnapshot).all()
    
    for snapshot in snapshots:
        suggestions = generate_suggestions_for_position(db, snapshot, quote_provider, now_eat)
        
        for sug in suggestions:
            # Create time bucket for hourly dedup (or similar)
            time_bucket = f"{now_eat.strftime('%Y-%m-%d-%H')}"
            
            # Persist if not already exists in this bucket
            try:
                # Check for existing
                existing = db.query(ManagementSuggestionLog).filter(
                    ManagementSuggestionLog.ticket_id == str(snapshot.id), # Linking via Ticket Row PK
                    ManagementSuggestionLog.suggestion_type == sug.suggestion_type.value,
                    ManagementSuggestionLog.time_bucket == time_bucket
                ).first()
                
                if not existing:
                    log_entry = ManagementSuggestionLog(
                        ticket_id=str(snapshot.id), 
                        broker_trade_id=sug.broker_trade_id,
                        suggestion_type=sug.suggestion_type.value,
                        severity=sug.severity,
                        data=sug.model_dump(mode="json"),
                        time_bucket=time_bucket,
                        expires_at=sug.expires_at_eat
                    )
                    db.add(log_entry)
                    db.commit()
                    logger.info(f"Generated suggestion {sug.suggestion_type} for ticket {sug.ticket_id}")
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to log suggestion: {e}")
