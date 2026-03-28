"""
shared/security/health.py
Unified health check utility for microservices.
Checks DB and Redis connectivity.
"""

import logging
from typing import Dict, Any
from sqlalchemy.orm import Session
from shared.messaging.event_bus import EventBus
from shared.database.session import get_db

logger = logging.getLogger("HealthCheck")

async def check_service_health(db: Session, bus: EventBus = None) -> Dict[str, Any]:
    """
    Performs a deep health check:
    - Pings Database
    - Pings Redis (if bus provided)
    """
    health = {
        "status": "healthy",
        "database": "unknown",
        "redis": "unknown"
    }
    
    # 1. Check Database
    try:
        db.execute("SELECT 1")
        health["database"] = "connected"
    except Exception as e:
        logger.error("HealthCheck: Database connection failed: %s", e)
        health["database"] = "disconnected"
        health["status"] = "unhealthy"

    # 2. Check Redis
    if bus:
        try:
            if bus.client.ping():
                health["redis"] = "connected"
            else:
                health["redis"] = "disconnected"
                health["status"] = "unhealthy"
        except Exception as e:
            logger.error("HealthCheck: Redis connection failed: %s", e)
            health["redis"] = "disconnected"
            health["status"] = "unhealthy"
    
    return health
