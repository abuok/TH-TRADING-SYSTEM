"""
shared/security/rate_limiting.py
---------------------------------
slowapi-based rate limiting for all TH-TRADING-SYSTEM FastAPI services.

Usage in a service::

    from shared.security.rate_limiting import limiter, setup_rate_limiting, LIMITS
    from fastapi import FastAPI, Request

    app = FastAPI()
    setup_rate_limiting(app)

    @app.get("/market/{pair}")
    @limiter.limit(LIMITS["default"])
    async def get_market(pair: str, request: Request):
        ...

The ``request: Request`` parameter is required by slowapi when using
the ``get_remote_address`` key function.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

# ── Rate limit definitions ────────────────────────────────────────────────────
# Format: "<count>/<period>"   period = second | minute | hour | day

LIMITS: dict[str, str] = {
    "default":    "100/minute",    # Generic public endpoints
    "dashboard":  "300/minute",    # Dashboard page requests
    "evaluation": "500/minute",    # Risk evaluation (high-frequency internal)
    "health":     "1000/minute",   # Health checks (monitoring probes)
    "write":      "60/minute",     # State-mutating endpoints (approve, reject)
    "internal":   "5000/minute",   # Service-to-service (relaxed)
}

# ── Limiter instance (import this in services) ────────────────────────────────
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[LIMITS["default"]],
)


# ── FastAPI wiring ─────────────────────────────────────────────────────────────

def setup_rate_limiting(app: FastAPI) -> None:
    """
    Attach the rate limiter to a FastAPI application.

    Call once during app initialisation::

        app = FastAPI()
        setup_rate_limiting(app)
    """
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)
    logger.info("Rate limiting enabled (default: %s)", LIMITS["default"])


async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Return structured 429 response with retry guidance."""
    retry_after = str(exc.detail).split("in ")[-1] if "in " in str(exc.detail) else "60s"
    logger.warning(
        "Rate limit hit | path=%s remote=%s limit=%s",
        request.url.path,
        request.client.host if request.client else "unknown",
        exc.detail,
    )
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "detail": str(exc.detail),
            "retry_after": retry_after,
        },
        headers={"Retry-After": retry_after},
    )
