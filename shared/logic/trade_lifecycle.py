from sqlalchemy import and_
from sqlalchemy.orm import Session

from shared.logic.matching import match_fill_to_ticket
from shared.database.models import (
    IncidentLog,
    JournalLog,
    OrderTicket,
    TicketTradeLink,
    TradeFillLog,
)
from shared.providers.symbol_spec import get_symbol_spec_provider
from shared.types.trade_capture import TradeFillEvent


def process_trade_fill(db: Session, fill: TradeFillEvent):
    """
    Processes a trade fill event: logs it, matches to ticket, and updates lifecycle.
    """
    # 1. Deduplication (check if this specific fill event seen before)
    # The DB UniqueConstraint handles this at commit time, but we can check early
    existing_fill = (
        db.query(TradeFillLog)
        .filter(
            and_(
                TradeFillLog.broker_trade_id == fill.broker_trade_id,
                TradeFillLog.event_type == fill.event_type,
                TradeFillLog.time_utc == fill.time_utc,
            )
        )
        .first()
    )

    if existing_fill:
        return {"status": "ignored", "reason": "duplicate fill"}

    # 2. Save Fill Log
    new_fill_log = TradeFillLog(
        broker_trade_id=fill.broker_trade_id,
        symbol=fill.symbol,
        side=fill.side,
        lots=fill.lots,
        price=fill.price,
        time_utc=fill.time_utc,
        time_eat=fill.time_eat,
        event_type=fill.event_type,
        sl=fill.sl,
        tp=fill.tp,
        comment=fill.comment,
        magic=fill.magic,
        account_id=fill.account_id,
        source=fill.source,
    )
    db.add(new_fill_log)

    # 3. Ticket Matching & Linking
    ticket_id, method, match_score = match_fill_to_ticket(db, fill)

    if ticket_id:
        # Link fill to ticket if not already linked for this broker_trade_id
        existing_link = (
            db.query(TicketTradeLink)
            .filter(TicketTradeLink.broker_trade_id == fill.broker_trade_id)
            .first()
        )

        if not existing_link:
            link = TicketTradeLink(
                ticket_id=ticket_id,
                broker_trade_id=fill.broker_trade_id,
                match_method=method,
                match_score=match_score,
            )
            db.add(link)

        # 4. Lifecycle Updates
        ticket = (
            db.query(OrderTicket).filter(OrderTicket.ticket_id == ticket_id).first()
        )
        if fill.event_type == "OPEN":
            ticket.status = "EXECUTED"
            ticket.executed_at = fill.time_utc

            # Journal Entry
            journal = JournalLog(
                ticket_id=ticket_id,
                event_type="TRADE_OPENED",
                message=f"Trade opened on MT5 (ID: {fill.broker_trade_id}) at {fill.price}",
                data={
                    "broker_trade_id": fill.broker_trade_id,
                    "price": fill.price,
                    "lots": fill.lots,
                },
            )
            db.add(journal)

        elif fill.event_type in ["CLOSE", "PARTIAL"]:
            # Calculate Realized R
            r_gain = calculate_realized_r(ticket, fill)
            
            # Update hindsight tracking
            if ticket.hindsight_realized_r is None:
                ticket.hindsight_realized_r = 0.0
            
            ticket.hindsight_realized_r += r_gain
            new_r = ticket.hindsight_realized_r

            if fill.event_type == "CLOSE":
                ticket.status = "CLOSED"
                ticket.closed_at = fill.time_utc
                journal_type = "TRADE_CLOSED"
                msg = f"Trade fully closed on MT5. Realized R: {new_r:.2f}"
            else:
                journal_type = "TRADE_PARTIAL"
                msg = f"Partial close on MT5. Lots: {fill.lots}. R gain: {r_gain:.2f}"

            journal = JournalLog(
                ticket_id=ticket_id,
                event_type=journal_type,
                message=msg,
                data={
                    "broker_trade_id": fill.broker_trade_id,
                    "price": fill.price,
                    "lots": fill.lots,
                    "r_gain": r_gain,
                },
            )
            db.add(journal)
    else:
        # Unmatched fill - log as incident
        incident = IncidentLog(
            severity="WARNING",
            component="Bridge",
            message=f"UNMATCHED {fill.event_type} fill for {fill.symbol} {fill.side} (ID: {fill.broker_trade_id})",
            context={"fill": fill.model_dump(mode="json")},
        )
        db.add(incident)

    db.commit()
    return {
        "status": "success",
        "matched": ticket_id is not None,
        "ticket_id": ticket_id,
    }


def calculate_realized_r(ticket: OrderTicket, fill: TradeFillEvent) -> float:
    """
    Calculates R gain/loss for a fill event.
    Formula: R = (ExitPrice - EntryPrice) * Multiplier / RiskUSD
    """
    if not ticket.entry_price or ticket.risk_usd == 0:
        return 0.0

    # Get symbol spec for tick value/size
    spec_provider = get_symbol_spec_provider()
    spec = spec_provider.get_spec(ticket.pair)
    if not spec:
        return 0.0

    price_diff = fill.price - ticket.entry_price
    if ticket.direction == "SELL":
        price_diff = -price_diff

    ticks = price_diff / spec.tick_size
    # PnL = lots * ticks * tick_value
    pnl = fill.lots * ticks * spec.tick_value

    r_gain = pnl / ticket.risk_usd
    return r_gain
