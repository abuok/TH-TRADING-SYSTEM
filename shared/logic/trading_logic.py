import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from shared.database.models import OrderTicket
from shared.types.packets import (
    AlignmentDecision,
    RiskApprovalPacket,
    TechnicalSetupPacket,
)


def generate_order_ticket(
    setup: TechnicalSetupPacket,
    risk: RiskApprovalPacket,
    db: Session,
    risk_usd: float = 100.0,
    alignment: AlignmentDecision | None = None,
) -> OrderTicket:
    """
    Generates an OrderTicket from setup and risk packets.
    Handles idempotency and lot sizing.
    """
    # Idempotency key
    raw_key = (
        f"{setup.asset_pair}_{setup.strategy_name}_{setup.timestamp}_{risk.timestamp}"
    )
    idempotency_key = hashlib.sha256(raw_key.encode()).hexdigest()

    # Check for existing
    existing = (
        db.query(OrderTicket)
        .filter(OrderTicket.idempotency_key == idempotency_key)
        .first()
    )
    if existing:
        return existing

    # Direction
    direction = "BUY" if setup.take_profit > setup.entry_price else "SELL"

    # Lot Sizing via SymbolSpecProvider
    from shared.providers.symbol_spec import get_symbol_spec_provider

    spec_provider = get_symbol_spec_provider()
    spec = spec_provider.get_spec(setup.asset_pair)

    status = "PENDING"
    block_reason = None

    if not spec:
        status = "BLOCKED"
        block_reason = f"[BRIDGE] No SymbolSpec found for {setup.asset_pair}. Lot sizing impossible."
        lots = 0.0
    else:
        dist = abs(setup.entry_price - setup.stop_loss)
        if dist == 0:
            lots = spec.min_lot
        else:
            ticks = dist / spec.tick_size
            if ticks == 0:
                lots = spec.min_lot
            else:
                raw_lots = risk_usd / (ticks * spec.tick_value)
                lots = round(max(spec.min_lot, raw_lots), 2)
                remainder = lots % spec.lot_step
                if remainder > 1e-9:
                    lots = round(lots - remainder, 2)

    dist = abs(setup.entry_price - setup.stop_loss)
    rr_tp1 = abs(setup.take_profit - setup.entry_price) / dist if dist > 0 else 0.0

    # Status check: alignment and risk engine logic
    if status != "BLOCKED":
        if alignment and not alignment.is_aligned:
            status = "BLOCKED"
            block_reason = f"[ALIGNMENT] {'; '.join(alignment.reason_codes) if alignment.reason_codes else 'Strategy constitution violation'}"
        elif risk.status == "BLOCK":
            status = "BLOCKED"
            block_reason = (
                ", ".join(risk.reasons) if risk.reasons else "Risk engine rejected."
            )

    expires_at = (
        datetime.now(timezone.utc) + timedelta(minutes=15)
        if status == "PENDING"
        else None
    )

    # Note: alignment_score is left as None or a placeholder as binary alignment doesn't use it for gating.
    # If setup quality metrics are added later, they can populate this.
    ticket = OrderTicket(
        ticket_id=f"TKT-{uuid.uuid4().hex[:8].upper()}",
        setup_packet_id=0,
        risk_packet_id=0,
        pair=setup.asset_pair,
        direction=direction,
        entry_price=setup.entry_price,
        stop_loss=setup.stop_loss,
        take_profit_1=setup.take_profit,
        lot_size=lots,
        risk_usd=risk_usd,
        risk_pct=0.5,
        rr_tp1=rr_tp1,
        status=status,
        block_reason=block_reason,
        idempotency_key=idempotency_key,
        expires_at=expires_at,
        # NOTE: alignment_score / is_aligned / alignment_summary columns are
        # currently commented out in models.py (schema debt — pending migration).
        # Do NOT pass them here until schema is aligned.
        active_policy_name=None,
        active_policy_hash=None,
    )

    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket
