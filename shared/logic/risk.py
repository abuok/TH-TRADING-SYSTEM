from typing import Dict
from shared.types.packets import (
    TechnicalSetupPacket,
    MarketContextPacket,
    RiskApprovalPacket,
)
from datetime import datetime
import pytz


class RiskEngine:
    def __init__(self, config: Dict):
        """
        config example:
        {
            "max_daily_loss": 30.0,
            "max_total_loss": 100.0,
            "max_consecutive_losses": 2,
            "min_rr_threshold": 2.0,
            "lot_size_limit": 0.1,
            "account_balance": 1000.0
        }
        """
        self.config = config

    def calculate_rr(self, setup: TechnicalSetupPacket) -> float:
        risk = abs(setup.entry_price - setup.stop_loss)
        reward = abs(setup.take_profit - setup.entry_price)
        if risk == 0:
            return 0.0
        return round(reward / risk, 2)

    def is_in_event_window(
        self, setup_time: datetime, context: MarketContextPacket
    ) -> bool:
        # Ensure setup_time is timezone aware
        if setup_time.tzinfo is None:
            setup_time = setup_time.replace(tzinfo=pytz.UTC)

        windows = context.no_trade_windows
        for window in windows:
            try:
                start = datetime.fromisoformat(window["start"])
                end = datetime.fromisoformat(window["end"])

                # Align timezones for comparison
                if start.tzinfo is None:
                    start = start.replace(tzinfo=pytz.UTC)
                if end.tzinfo is None:
                    end = end.replace(tzinfo=pytz.UTC)

                if start <= setup_time <= end:
                    return True
            except (KeyError, ValueError, TypeError):
                continue
        return False

    def evaluate(
        self,
        setup: TechnicalSetupPacket,
        context: MarketContextPacket,
        account_state: Dict,
    ) -> RiskApprovalPacket:
        """
        account_state example:
        {
            "daily_loss": 0.0,
            "total_loss": 0.0,
            "consecutive_losses": 0
        }
        """
        reasons = []
        status = "ALLOW"
        is_approved = True

        # 0. Context Staleness Check (Fail Closed)
        now_utc = datetime.now(pytz.UTC)
        context_age = (now_utc - context.timestamp).total_seconds()
        if context_age > 7200:  # 2 hours
            status = "BLOCK"
            is_approved = False
            reasons.append(
                f"Market context is stale ({context_age / 60:.1f} mins old). Fail-safe block triggered."
            )

        # 1. RR Check
        rr = self.calculate_rr(setup)
        if rr < self.config["min_rr_threshold"]:
            status = "BLOCK"
            is_approved = False
            reasons.append(
                f"RR Ratio {rr} below threshold {self.config['min_rr_threshold']}"
            )

        # 2. Daily Loss Check
        if account_state["daily_loss"] >= self.config["max_daily_loss"]:
            status = "BLOCK"
            is_approved = False
            reasons.append(f"Daily loss limit reached: ${account_state['daily_loss']}")

        # 3. Consecutive Losses Check
        if account_state["consecutive_losses"] >= self.config["max_consecutive_losses"]:
            status = "BLOCK"
            is_approved = False
            reasons.append(
                f"Max consecutive losses reached: {account_state['consecutive_losses']}"
            )

        # 4. Event Window Check
        if self.is_in_event_window(setup.timestamp, context):
            status = "BLOCK"
            is_approved = False
            reasons.append("Trade falls within a high-impact economic event window")

        # 5. Position Size (Lot Size)
        # Placeholder for complex lot size calculation
        max_pos = self.config["lot_size_limit"]

        return RiskApprovalPacket(
            schema_version="1.0.0",
            request_id=f"risk_{datetime.now().timestamp()}",
            status=status,
            is_approved=is_approved,
            risk_score=100.0 if is_approved else 0.0,
            max_position_size=max_pos,
            rr_ratio=rr,
            approver="DeterministicRiskEngineV1",
            reasons=reasons,
        )
