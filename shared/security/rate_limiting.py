"""
shared/security/rate_limiting.py
--------------------------------
Redis-backed rate limiting for FastAPI.
"""

import time
from functools import wraps
from fastapi import HTTPException
from shared.messaging.event_bus import EventBus
from shared.config.settings import settings

def rate_limit(name: str, seconds: int = None):
    """
    Simple rate limiter using Redis.
    Prevent execution if the last call was within 'seconds' window.
    """
    if seconds is None:
        seconds = settings.RATE_LIMIT_SECONDS

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            bus = EventBus()
            key = f"rate_limit:{name}"
            
            last_call = bus.client.get(key)
            now = time.time()
            
            if last_call:
                elapsed = now - float(last_call)
                if elapsed < seconds:
                    remaining = int(seconds - elapsed)
                    raise HTTPException(
                        status_code=429,
                        detail=f"Rate limit exceeded. Try again in {remaining}s."
                    )
            
            # Update last call time
            bus.client.setex(key, seconds, str(now))
            return await func(*args, **kwargs)
            
        return wrapper
    return decorator
