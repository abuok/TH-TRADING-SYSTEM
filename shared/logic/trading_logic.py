from datetime import datetime, timezone
import uuid
import hashlib
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from shared.database.models import OrderTicket, Packet
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
    
    # Lot Sizing (Simple Contract Model for Demo)
    # Dist = abs(Entry - SL)
    # Lots = Risk / (Dist * ContractFactor)
    dist = abs(setup.entry_price - setup.stop_loss)
    if dist == 0:
        lots = 0.1
    else:
        # XAUUSD: $1 move (100 pips) = $100 per lot. ContractFactor = 100.
        # GBPJPY: 100 pips = approx $6.5 per lot. ContractFactor = 650.
        factor = 100.0 if "XAU" in setup.asset_pair else 100000.0
        lots = round(max(0.01, risk_usd / (dist * factor)), 2) if dist > 0 else 0.01

    # RR Ratios
    rr_tp1 = abs(setup.take_profit - setup.entry_price) / dist if dist > 0 else 0.0
    
    # Status: guardrails hard_block takes precedence over risk engine
    status = "PENDING"
    block_reason = None
    if guardrails and guardrails.hard_block:
        status = "BLOCKED"
        block_reason = f"[GUARDRAILS] {guardrails.primary_block_reason or 'Strategy constitution violation'}"
    elif risk.status == "BLOCK":
        status = "BLOCKED"
        block_reason = ", ".join(risk.reasons) if risk.reasons else "Risk engine rejected."

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
        guardrails_score=guardrails.discipline_score if guardrails else None,
        guardrails_hard_block=guardrails.hard_block if guardrails else False,
        guardrails_summary=[
            {"id": i.id, "name": i.name, "status": i.status, "details": i.details}
            for i in guardrails.top_issues
        ] if guardrails else None,
    )
    
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket
