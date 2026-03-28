"""
shared/logic/metrics_aggregator.py
---------------------------------
Background task to compute and cache account metrics.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from shared.database.session import get_transactional_db
from shared.logic.accounts import calculate_account_state
from shared.messaging.event_bus import EventBus

logger = logging.getLogger("MetricsAggregator")

class MetricsAggregator:
    def __init__(self, interval_seconds: int = 5):
        self.interval = interval_seconds
        self.bus = EventBus()
        self.is_running = False
        self.redis_key = "account:state:latest"

    async def run(self):
        """Main loop for computing and caching metrics."""
        self.is_running = True
        logger.info("Metrics Aggregator started. Interval: %ss", self.interval)
        
        while self.is_running:
            try:
                with get_transactional_db() as db:
                    # Calculate real state from DB
                    state = calculate_account_state(db, force_refresh=True)
                    
                    # Add timestamp for staleness tracking
                    state["updated_at"] = datetime.now(timezone.utc).isoformat()
                    
                    # Cache to Redis
                    self.bus.client.set(self.redis_key, json.dumps(state))
                    
                await asyncio.sleep(self.interval)
            except Exception as e:
                logger.error("Error in Metrics Aggregator: %s", e)
                await asyncio.sleep(self.interval)

    def stop(self):
        self.is_running = False
