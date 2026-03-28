"""
shared/logic/accounts.py
Shared logic for fetching and calculating account-level stats (PnL, R, losses).
"""

from datetime import datetime, timezone
from typing import Any, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session
from shared.database.models import OrderTicket

def calculate_account_state(db: Session, config: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Fetch current daily loss and consecutive losses from DB."""
    if config is None:
        config = {}
        
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 1. Daily Loss (Sum of outcomes for today where < 0)
    # Priority: manual_outcome_r -> hindsight_realized_r
    from sqlalchemy.sql import coalesce
    
    net_r = db.query(func.sum(coalesce(OrderTicket.manual_outcome_r, OrderTicket.hindsight_realized_r))).filter(
        OrderTicket.closed_at >= today_start
    ).scalar() or 0.0
    
    # 2. Consecutive Losses (Count backwards until a win)
    last_trades = db.query(OrderTicket).filter(
        OrderTicket.status == "CLOSED"
    ).order_by(OrderTicket.closed_at.desc()).limit(10).all()
    
    consecutive_losses = 0
    last_loss_time = None
    
    for i, t in enumerate(last_trades):
        effective_r = t.manual_outcome_r if t.manual_outcome_r is not None else t.hindsight_realized_r
        if (effective_r or 0) < 0:
            consecutive_losses += 1
            if i == 0:
                last_loss_time = t.closed_at
        else:
            break
            
    return {
        "daily_loss": abs(net_r) if net_r < 0 else 0.0,
        "net_r": net_r,
        "consecutive_losses": consecutive_losses,
        "last_loss_time": last_loss_time,
        "account_balance": config.get("account_balance", 10000.0)
    }
