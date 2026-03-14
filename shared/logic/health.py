"""Health check utilities for services."""

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


async def health_check(db: Session = None) -> dict[str, Any]:
    """Get comprehensive health status of the service.

    Args:
        db: Database session for connectivity check

    Returns:
        Dictionary with service health status
    """
    health = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {},
    }

    # Database connectivity check
    if db:
        try:
            db.execute(text("SELECT 1"))
            health["checks"]["database"] = {"status": "ok"}
        except Exception as e:
            health["checks"]["database"] = {"status": "error", "detail": str(e)}
            health["status"] = "degraded"

    return health
