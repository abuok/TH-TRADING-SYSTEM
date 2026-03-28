import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from shared.database.models import OrderTicket, AuditLog
from shared.messaging.event_bus import EventBus
from shared.types.trading import SkipReasonEnum, TicketOutcomeEnum

logger = logging.getLogger("TicketQueueLogic")
event_bus = EventBus()


def _log_transition(ticket_id: str, transition_type: str, details: dict):
    """Helper to send transitions to the Journal Service via Event Bus."""
    try:
        event_bus.publish(
            "journal_events",
            {
                "event_type": "ticket_transition",
                "ticket_id": ticket_id,
                "transition_type": transition_type,
                "details": details,
            },
        )
    except Exception as e:
        logger.warning(
            f"Failed to log transition {transition_type} for {ticket_id} via EventBus: {e}"
        )


def approve_ticket(db: Session, ticket_id: str, actor: str = "system") -> OrderTicket:
    """Marks a ticket as APPROVED and active."""
    ticket = db.query(OrderTicket).filter(OrderTicket.ticket_id == ticket_id).first()
    if not ticket:
        raise ValueError(f"Ticket {ticket_id} not found")

    if ticket.status != "IN_REVIEW":
        raise ValueError(
            f"Ticket must be IN_REVIEW to approve. Currently: {ticket.status}"
        )

    ticket.status = "APPROVED"
    ticket.reviewed_at = datetime.now(timezone.utc)
    ticket.review_decision = "APPROVE"

    db.commit()
    db.refresh(ticket)

    _log_transition(
        ticket.ticket_id, "APPROVED", {"reviewed_at": ticket.reviewed_at.isoformat()}
    )
    
    # NEW: Institutional Audit Log
    audit = AuditLog(
        actor=actor,
        action="TICKET_APPROVED",
        resource_type="OrderTicket",
        resource_id=ticket.ticket_id,
        after_state={"status": "APPROVED", "reviewed_at": ticket.reviewed_at.isoformat()},
        change_reason="Manual Operator Approval from Dashboard"
    )
    db.add(audit)
    db.commit()

    return ticket


def skip_ticket(
    db: Session, ticket_id: str, reason: SkipReasonEnum, notes: str | None = None, actor: str = "system"
) -> OrderTicket:
    """Marks a ticket as SKIPPED with a reason."""
    ticket = db.query(OrderTicket).filter(OrderTicket.ticket_id == ticket_id).first()
    if not ticket:
        raise ValueError(f"Ticket {ticket_id} not found")

    if ticket.status != "IN_REVIEW":
        raise ValueError(
            f"Ticket must be IN_REVIEW to skip. Currently: {ticket.status}"
        )

    ticket.status = "SKIPPED"
    ticket.reviewed_at = datetime.now(timezone.utc)
    ticket.review_decision = "SKIP"
    ticket.skip_reason = reason.value
    ticket.notes = notes

    db.commit()
    db.refresh(ticket)

    _log_transition(
        ticket.ticket_id,
        "SKIPPED",
        {
            "reviewed_at": ticket.reviewed_at.isoformat(),
            "reason": reason.value,
            "notes": notes,
        },
    )

    # NEW: Institutional Audit Log
    audit = AuditLog(
        actor=actor,
        action="TICKET_SKIPPED",
        resource_type="OrderTicket",
        resource_id=ticket.ticket_id,
        after_state={
            "status": "SKIPPED",
            "reason": reason.value,
            "reviewed_at": ticket.reviewed_at.isoformat()
        },
        change_reason=f"Manual Operator Skip: {reason.value}"
    )
    db.add(audit)
    db.commit()

    return ticket


def close_ticket(
    db: Session,
    ticket_id: str,
    outcome: TicketOutcomeEnum,
    exit_price: float | None = None,
    realized_r: float | None = None,
    screenshot_ref: str | None = None,
) -> OrderTicket:
    """Marks an APPROVED ticket as CLOSED with final outcome attributes."""
    ticket = db.query(OrderTicket).filter(OrderTicket.ticket_id == ticket_id).first()
    if not ticket:
        raise ValueError(f"Ticket {ticket_id} not found")

    if ticket.status != "APPROVED":
        raise ValueError(
            f"Ticket must be APPROVED to close. Currently: {ticket.status}"
        )

    ticket.status = "CLOSED"
    ticket.closed_at = datetime.now(timezone.utc)
    ticket.manual_exit_price = exit_price
    ticket.manual_outcome_r = realized_r
    ticket.manual_outcome_label = outcome.value
    ticket.manual_screenshot_ref = screenshot_ref

    db.commit()
    db.refresh(ticket)

    _log_transition(
        ticket.ticket_id,
        "CLOSED",
        {
            "closed_at": ticket.closed_at.isoformat(),
            "outcome": outcome.value,
            "realized_r": realized_r,
            "exit_price": exit_price,
        },
    )
    return ticket


def auto_expire_tickets(db: Session) -> int:
    """Finds all IN_REVIEW tickets past their expiry and changes to EXPIRED."""
    now = datetime.now(timezone.utc)

    expired_tickets = (
        db.query(OrderTicket)
        .filter(OrderTicket.status == "IN_REVIEW", OrderTicket.expires_at <= now)
        .all()
    )

    count = 0
    for ticket in expired_tickets:
        ticket.status = "EXPIRED"
        ticket.reviewed_at = now
        _log_transition(ticket.ticket_id, "EXPIRED", {"expired_at": now.isoformat()})
        count += 1

    if count > 0:
        db.commit()

    return count
