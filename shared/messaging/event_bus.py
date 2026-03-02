import os
import json
import redis
from datetime import datetime

class EventBus:
    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.client = redis.from_url(self.redis_url, decode_responses=True)

    def publish(self, stream_name: str, data: dict):
        """Publish a packet to a Redis stream."""
        # Ensure data is serializable
        if "timestamp" in data and isinstance(data["timestamp"], datetime):
            data["timestamp"] = data["timestamp"].isoformat()
            
        return self.client.xadd(stream_name, {"payload": json.dumps(data)})

    def subscribe(self, stream_name: str, group_name: str, consumer_name: str):
        """Create a consumer group if it doesn't exist."""
        try:
            self.client.xgroup_create(stream_name, group_name, id="0", mkstream=True)
        except redis.exceptions.ResponseError as e:
            if "already exists" not in str(e):
                raise e

    def consume(self, stream_name: str, group_name: str, consumer_name: str, count: int = 1):
        """Read pending messages from a stream."""
        return self.client.xreadgroup(group_name, consumer_name, {stream_name: ">"}, count=count)
