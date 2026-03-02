from datetime import datetime, timezone
import uuid
import hashlib
from typing import Optional
from sqlalchemy.orm import Session

from shared.database.models import OrderTicket
from shared.types.packets import TechnicalSetupPacket, RiskApprovalPacket
from shared.types.guardrails import GuardrailsResult

def generate_order_ticket(
    setup: TechnicalSetupPacket,
    risk: RiskApprovalPacket,
    db: Session,
    risk_usd: float = 100.0,
    guardrails: Optional[GuardrailsResult] = None,
) -> OrderTicket:
    """
    Generates an OrderTicket from setup and risk packets.
    Handles idempotency and lot sizing.
    """
    # Idempotency key: hash of both packet IDs/timestamps to ensure unique pair
    # In a real system we'd use setup.id + risk.id, but here they might be from memory
    # so we use a combination of pair + strategy + timestamp
    # Actually, setup has a timestamp, risk has a timestamp.
    raw_key = f"{setup.asset_pair}_{setup.strategy_name}_{setup.timestamp}_{risk.timestamp}"
    idempotency_key = hashlib.sha256(raw_key.encode()).hexdigest()

    # Check for existing
    existing = db.query(OrderTicket).filter(OrderTicket.idempotency_key == idempotency_key).first()
    if existing:
        return existing

    # Direction
    direction = "BUY" if setup.take_profit > setup.entry_price else "SELL"
    
    # Lot Sizing via SymbolSpecProvider
    from shared.providers.symbol_spec import get_symbol_spec_provider
    spec_provider = get_symbol_spec_provider()
    spec = spec_provider.get_spec(setup.asset_pair)
    
    status = "IN_REVIEW"
    block_reason = None

    if not spec:
        # FAIL CLOSED: No symbol spec found for this pair
        status = "BLOCKED"
        block_reason = f"[BRIDGE] No SymbolSpec found for {setup.asset_pair}. Lot sizing impossible."
        lots = 0.0
    else:
        dist = abs(setup.entry_price - setup.stop_loss)
        if dist == 0:
            lots = spec.min_lot
        else:
            # Risk/Lot = RiskUSD / (Dist * TickValue/TickSize * ContractSize??)
            # Standard MT5 formula: Lots = RiskUSD / (StopLossDistanceInTicks * TickValue)
            # Here dist is in price units. Ticks = dist / tick_size.
            ticks = dist / spec.tick_size
            if ticks == 0:
                lots = spec.min_lot
            else:
                # Formula: Risk = Lots * Ticks * TickValue
                # => Lots = Risk / (Ticks * TickValue)
                raw_lots = risk_usd / (ticks * spec.tick_value)
                # Apply min_lot and lot_step
                lots = round(max(spec.min_lot, raw_lots), 2) # simplified rounding
                # Ensure it's a multiple of lot_step
                remainder = lots % spec.lot_step
                if remainder > 1e-9:
                    lots = round(lots - remainder, 2)
    
    dist = abs(setup.entry_price - setup.stop_loss)

    # RR Ratios
    rr_tp1 = abs(setup.take_profit - setup.entry_price) / dist if dist > 0 else 0.0
    
    # Status check: guardrails and risk engine logic
    # Only update status if not already BLOCKED by bridge/missing spec
    if status != "BLOCKED":
        if guardrails and guardrails.hard_block:
            status = "BLOCKED"
            block_reason = f"[GUARDRAILS] {guardrails.primary_block_reason or 'Strategy constitution violation'}"
        elif risk.status == "BLOCK":
            status = "BLOCKED"
            block_reason = ", ".join(risk.reasons) if risk.reasons else "Risk engine rejected."

    from datetime import timedelta
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15) if status == "IN_REVIEW" else None

    ticket = OrderTicket(
        ticket_id=f"TKT-{uuid.uuid4().hex[:8].upper()}",
        setup_packet_id=0, # placeholders, to be filled by caller if packets are in DB
        risk_packet_id=0,
        pair=setup.asset_pair,
        direction=direction,
        entry_price=setup.entry_price,
        stop_loss=setup.stop_loss,
        take_profit_1=setup.take_profit,
        lot_size=lots,
        risk_usd=risk_usd,
        risk_pct=0.5, # placeholder 0.5%
        rr_tp1=rr_tp1,
        status=status,
        block_reason=block_reason,
        idempotency_key=idempotency_key,
        expires_at=expires_at,
        guardrails_score=guardrails.discipline_score if guardrails else None,
        guardrails_hard_block=guardrails.hard_block if guardrails else False,
        guardrails_summary=[
            {"id": i.id, "name": i.name, "status": i.status, "details": i.details}
            for i in guardrails.top_issues
        ] if guardrails else None,
        active_policy_name=guardrails.policy_name if guardrails else None,
        active_policy_hash=guardrails.policy_hash if guardrails else None,
    )
    
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket
