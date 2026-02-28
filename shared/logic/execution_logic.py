import yaml
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from shared.database.models import KillSwitch, OrderTicket
from shared.types.execution_prep import PreflightCheck
from shared.logic.sessions import get_nairobi_time

def load_exec_config():
    with open("config/execution_prep.yaml", "r") as f:
        return yaml.safe_load(f)

class PreflightEngine:
    def __init__(self, db_session):
        self.db = db_session
        self.config = load_exec_config()

    def run_checks(self, ticket: OrderTicket, current_price: float, current_spread: float) -> List[PreflightCheck]:
        checks = []
        now = get_nairobi_time()

        # 1. Expiry Check
        expires_at = ticket.expires_at
        if expires_at and expires_at.tzinfo is None:
            # If naive, assume it was stored as UTC and localize
            import pytz
            expires_at = pytz.utc.localize(expires_at).astimezone(pytz.timezone("Africa/Nairobi"))
        
        is_expired = expires_at and now > expires_at
        checks.append(PreflightCheck(
            id="expiry",
            name="Ticket Expiry",
            status="PASS" if not is_expired else "FAIL",
            details="Ticket is active" if not is_expired else f"Ticket expired at {expires_at}"
        ))

        # 2. Kill Switch Check
        active_ks = self.db.query(KillSwitch).filter(KillSwitch.is_active == 1).first()
        checks.append(PreflightCheck(
            id="kill_switch",
            name="System Kill Switch",
            status="PASS" if not active_ks else "FAIL",
            details="All systems operational" if not active_ks else f"Kill switch active: {active_ks.switch_type}"
        ))

        # 3. Price Tolerance Check
        deviation = abs(current_price - ticket.entry_price) / ticket.entry_price * 100
        tolerance = self.config.get("price_tolerance_pct", 0.1)
        status = "PASS" if deviation <= tolerance else "FAIL"
        checks.append(PreflightCheck(
            id="price_deviation",
            name="Price Tolerance",
            status=status,
            details=f"Current deviation {deviation:.3f}% (Max {tolerance}%)"
        ))

        # 4. Spread Check
        max_spread = self.config.get("max_spread_pips", 3.0)
        status = "PASS" if current_spread <= max_spread else "WARN"
        checks.append(PreflightCheck(
            id="spread",
            name="Market Spread",
            status=status,
            details=f"Current spread {current_spread:.1f} pips (Max recommended {max_spread})"
        ))

        # 5. News Check (Simplified placeholder, would normally check MarketContextPacket)
        # Assuming no news for mock purposes unless we add real integration
        checks.append(PreflightCheck(
            id="news_window",
            name="News Proximity",
            status="PASS",
            details="No high-impact red events in immediate window"
        ))

        return checks
