"""
shared/logic/audit.py
---------------------
Structured audit trail for all critical trading system actions.

Every state transition (ticket approve/reject, trade open/close, lockout
apply/release) must call ``audit_action`` so there is a compliance-grade
record of who did what and when.

Usage::

    audit_action(
        db=db,
        actor="orchestration-service",
        action="TICKET_APPROVED",
        resource_type="OrderTicket",
        resource_id=ticket_id,
        before_state=before,
        after_state=ticket.dict(),
        request=request,          # optional FastAPI Request
    )
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def audit_action(
    db: Session,
    *,
    actor: str,
    action: str,
    resource_type: str,
    resource_id: str,
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
    change_reason: str | None = None,
    request: Any | None = None,  # FastAPI Request (optional)
) -> None:
    """
    Insert an immutable audit log row for a system action.

    Args:
        db:            Active SQLAlchemy session.
        actor:         Service name or user identifier performing the action.
        action:        Uppercase verb, e.g. ``"TICKET_APPROVED"``.
        resource_type: Model name, e.g. ``"OrderTicket"``.
        resource_id:   Primary identifier of the resource being acted on.
        before_state:  Snapshot of the resource *before* the change.
        after_state:   Snapshot of the resource *after* the change.
        change_reason: Human-readable reason for the change.
        request:       FastAPI ``Request`` object for IP / user-agent capture.
    """
    try:
        # Import here to avoid circular dependency at module load time
        from shared.database.models import AuditLog  # type: ignore[import]

        ip_address: str | None = None
        user_agent: str | None = None

        if request is not None:
            try:
                ip_address = request.client.host if request.client else None
                user_agent = request.headers.get("user-agent")
            except Exception:
                pass  # Defensive — never let audit fail due to request parsing

        entry = AuditLog(
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            before_state=before_state,
            after_state=after_state,
            change_reason=change_reason,
            ip_address=ip_address,
            user_agent=user_agent,
            timestamp=datetime.now(timezone.utc),
        )
        db.add(entry)
        db.flush()  # Write to DB within current transaction — don't auto-commit

        logger.info(
            "AUDIT | actor=%s action=%s %s:%s",
            actor,
            action,
            resource_type,
            resource_id,
        )

    except Exception as exc:
        # Audit must NEVER crash the calling service.
        # Log the failure and continue — a missing audit row is better than
        # a failed trade operation.
        logger.error(
            "Audit log insertion failed (actor=%s action=%s %s:%s): %s",
            actor,
            action,
            resource_type,
            resource_id,
            exc,
            exc_info=True,
        )
