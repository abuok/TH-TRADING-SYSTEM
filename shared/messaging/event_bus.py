import os
import json
import redis
from datetime import datetime


class EventBus:
    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.client = redis.from_url(self.redis_url, decode_responses=True)

    def publish(self, stream_name: str, data: dict, retries: int = 3):
        """Publish a packet to a Redis stream with retries and incident logging."""
        import time
        import logging
        from shared.database.models import IncidentLog
        import shared.database.session as db_session

        logger = logging.getLogger("EventBus")

        # Ensure data is serializable
        if "timestamp" in data and isinstance(data["timestamp"], datetime):
            data["timestamp"] = data["timestamp"].isoformat()

        payload = {"payload": json.dumps(data)}

        for attempt in range(1, retries + 1):
            try:
                return self.client.xadd(stream_name, payload)
            except redis.exceptions.RedisError as e:
                logger.warning(
                    f"Redis publish failed to '{stream_name}' (attempt {attempt}/{retries}): {e}"
                )
                if attempt == retries:
                    # Exhausted retries: circuit broken, log CRITICAL incident
                    try:
                        db = db_session.SessionLocal()
                        incident = IncidentLog(
                            severity="CRITICAL",
                            component="EventBus",
                            message=f"CRITICAL: Failed to publish to {stream_name} after {retries} attempts. System may stall. Msg: {e}",
                        )
                        db.add(incident)
                        db.commit()
                        db.close()
                    except Exception as db_err:
                        logger.error(
                            f"EventBus: Failed to write IncidentLog for Redis failure: {db_err}"
                        )
                    return None  # Fail gracefully
                time.sleep(
                    0.5 * (2 ** (attempt - 1))
                )  # Exponential backoff (0.5s, 1.0s, 2.0s)

    def subscribe(self, stream_name: str, group_name: str, consumer_name: str):
        """Create a consumer group if it doesn't exist."""
        try:
            self.client.xgroup_create(stream_name, group_name, id="0", mkstream=True)
        except redis.exceptions.ResponseError as e:
            if "already exists" not in str(e):
                raise e

    def consume(
        self, stream_name: str, group_name: str, consumer_name: str, count: int = 1
    ):
        """Read pending messages from a stream."""
        return self.client.xreadgroup(
            group_name, consumer_name, {stream_name: ">"}, count=count
        )
