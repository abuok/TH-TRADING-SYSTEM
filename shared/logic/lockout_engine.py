"""
shared/logic/lockout_engine.py
Enforces systemic discipline lockouts and daily/consecutive loss limits.
Replaces fragmented checks in generic guardrails.
"""

from typing import Dict, Any, Tuple
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from shared.database.models import KillSwitch, DisciplineLockout
from shared.types.enums import LockoutState

class LockoutEngine:
    def __init__(self, config: Dict[str, Any]):
        """
        config example:
        {
            "max_daily_loss_pct": 2.0,
            "max_consecutive_losses": 3,
            "account_balance": 10000.0
        }
        """
        self.config = config

    def evaluate(self, account_state: Dict[str, Any], db: Session = None) -> Tuple[LockoutState, str]:
        """
        account_state example:
        {
            "daily_loss": 0.0,
            "consecutive_losses": 0
        }
        Evaluates current budget usage + kill-switch DB flags. Fail-closed on DB error.
        """
        # 1. Check Kill Switches if DB available
        if db:
            try:
                active_switch = db.query(KillSwitch).filter(KillSwitch.is_active == 1).first()
                if active_switch:
                    return LockoutState.HARD_LOCK, f"Kill switch active: {active_switch.switch_type}"
                
                # Also check if there's an active DisciplineLockout
                active_lockout = db.query(DisciplineLockout).filter(DisciplineLockout.is_resolved == False).first()
                if active_lockout:
                    return LockoutState.HARD_LOCK, f"Discipline Lockout active: {active_lockout.reason}"
            except Exception as e:
                # Fail-closed
                return LockoutState.HARD_LOCK, "Database unreachable for kill switch check"
        else:
            return LockoutState.HARD_LOCK, "No database connection provided for LockoutEngine"

        # 2. Daily Loss Limit
        max_daily_pct = float(self.config.get("max_daily_loss_pct", 2.0))
        balance = account_state.get("account_balance", 10000.0)
        daily_loss_amount = account_state.get("daily_loss", 0.0)
        daily_loss_pct = (daily_loss_amount / balance * 100.0) if balance > 0 else 0.0

        if daily_loss_pct >= max_daily_pct:
            return LockoutState.HARD_LOCK, f"Daily loss {daily_loss_pct:.1f}% >= limit {max_daily_pct}%"

        # 3. Consecutive Loss Limit
        max_consecutive = int(self.config.get("max_consecutive_losses", 3))
        consecutive = account_state.get("consecutive_losses", 0)
        
        if consecutive >= max_consecutive:
            return LockoutState.HARD_LOCK, f"Consecutive losses {consecutive} >= limit {max_consecutive}"

        # 4. Soft Locks (Approaching limits - e.g. within 0.5% or 1 loss away)
        if daily_loss_pct >= max_daily_pct - 0.5:
            return LockoutState.SOFT_LOCK, f"Daily loss {daily_loss_pct:.1f}% approaching limit {max_daily_pct}%"
            
        if consecutive >= max_consecutive - 1 and max_consecutive > 1:
            return LockoutState.SOFT_LOCK, f"Consecutive losses {consecutive} approaching limit {max_consecutive}"

        return LockoutState.TRADEABLE, "Budget and Kill Switches OK"
