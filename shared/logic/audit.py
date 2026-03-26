import logging
from typing import Any
from sqlalchemy.orm import Session
from shared.database.models import AuditLog

logger = logging.getLogger("AuditLib")

def audit_action(
    db: Session,
    actor: str,
    action: str,
    resource_type: str,
    resource_id: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    change_reason: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None
) -> None:
    """
    Persist an immutable audit entry for a critical state transition.
    """
    try:
        entry = AuditLog(
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id),
            before_state=before,
            after_state=after,
            change_reason=change_reason,
            ip_address=ip_address,
            user_agent=user_agent
        )
        db.add(entry)
        db.commit()
        logger.info(f"AUDIT | {actor} | {action} | {resource_type}:{resource_id}")
    except Exception as e:
        logger.error(f"Failed to write audit log: {e}", exc_info=True)
        db.rollback()
