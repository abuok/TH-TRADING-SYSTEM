import json
import logging
import os
from functools import wraps
from typing import Any, Callable

import redis

logger = logging.getLogger(__name__)


class CacheLayer:
    """
    Redis caching layer with graceful degradation.
    If Redis is unavailable, operations safely no-op and log warnings.
    """

    def __init__(self):
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        try:
            # Short socket timeout so we don't hang if Redis is dead
            self.client = redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=1.0)
            self.client.ping()
        except redis.RedisError as e:
            logger.warning(f"Redis unavailable, caching disabled. Error: {e}")
            self.client = None

    def get(self, key: str) -> Any | None:
        if not self.client:
            return None
        try:
            val = self.client.get(key)
            return json.loads(val) if val else None
        except Exception as e:
            logger.warning(f"Cache get failed for {key}: {e}")
            return None

    def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        if not self.client:
            return False
        try:
            self.client.setex(key, ttl, json.dumps(value))
            return True
        except Exception as e:
            logger.warning(f"Cache set failed for {key}: {e}")
            return False

    def delete(self, key: str) -> bool:
        if not self.client:
            return False
        try:
            self.client.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Cache delete failed for {key}: {e}")
            return False

    def clear(self) -> bool:
        if not self.client:
            return False
        try:
            self.client.flushdb()
            return True
        except Exception as e:
            logger.warning(f"Cache clear failed: {e}")
            return False


cache_layer = CacheLayer()


def cached_data(key_prefix: str, ttl_seconds: int = 300):
    """
    Decorator to automatically cache the JSON-serializable return value of a function.
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Compute a simplistic deterministic cache key based on args/kwargs
            # Note: For production, ensure args/kwargs string representations are stable.
            args_repr = str(args) + str(kwargs)
            # Use hash for simplicity, though in prod MD5/SHA is safer across python runs
            import hashlib
            h = hashlib.md5(args_repr.encode()).hexdigest()
            key = f"{key_prefix}:{h}"

            # Try to get from cache
            cached_val = cache_layer.get(key)
            if cached_val is not None:
                return cached_val

            # Compute and set
            val = func(*args, **kwargs)
            cache_layer.set(key, val, ttl_seconds)
            return val

        return wrapper

    return decorator
