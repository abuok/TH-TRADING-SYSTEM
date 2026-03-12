from typing import Dict
from shared.types.packets import (
    TechnicalSetupPacket,
    MarketContextPacket,
    RiskApprovalPacket,
)
from datetime import datetime, timezone
from shared.database.models import IncidentLog
from sqlalchemy.orm import Session


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

        return False
    def evaluate(
        self,
        setup: TechnicalSetupPacket,
        context: MarketContextPacket,
        account_state: Dict,
        db: Session = None,
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
        status = "BLOCK"  # FAIL-CLOSED: Default to BLOCK
        is_approved = False

        # 0. Context Staleness Check (Fail Closed)
        now_utc = datetime.now(timezone.utc)
        context_age = (now_utc - context.timestamp).total_seconds()

        # Tighten from 2h (7200s) to 5m (300s) for production safety
        STALENESS_LIMIT = 300

        if context_age > STALENESS_LIMIT:
            reasons.append(
                f"Market context is stale ({context_age / 60:.1f} mins old). Fail-safe block triggered."
            )

        # 1. RR Check
        rr = self.calculate_rr(setup)
        if rr < self.config["min_rr_threshold"]:
            reasons.append(
                f"RR Ratio {rr} below threshold {self.config['min_rr_threshold']}"
            )

        # Event Window and Daily Loss are now handled by AlignmentEngine and LockoutEngine

        # Result calculation: If no reasons for blocking, then we ALLOW
        if not reasons:
            status = "ALLOW"
            is_approved = True
        else:
            # Log incident for observability
            if db:
                try:
                    incident = IncidentLog(
                        severity="WARNING",
                        component="RiskEngine",
                        message=f"Risk Block for {setup.asset_pair}: {'; '.join(reasons)}",
                    )
                    db.add(incident)
                    db.commit()
                except Exception:
                    pass

        # 5. Position Size (Lot Size)
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
