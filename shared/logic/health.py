"""Health check utilities for services."""

from typing import Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text


async def health_check(db: Session = None) -> Dict[str, Any]:
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
