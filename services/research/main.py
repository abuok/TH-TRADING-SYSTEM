"""
services/research/main.py
PHX Research Service — v1.3 Standardized API for simulations and hindsight analysis.
"""

import logging
import os
from datetime import datetime

from fastapi import Depends, FastAPI, Request
from sqlalchemy.orm import Session

import shared.database.session as db_session
from shared.instrumentation.tracing import init_tracing, instrument_app
from shared.logic.metrics import metrics_registry
from shared.security.middleware import setup_exception_handlers
from shared.security.rate_limiting import LIMITS, limiter, setup_rate_limiting

logger = logging.getLogger("ResearchService")

app = FastAPI(title="PHX Research Service")

# Initialize v1.3 Core Logic
init_tracing("research")
setup_rate_limiting(app)
instrument_app(app)
setup_exception_handlers(app)

@app.on_event("startup")
async def startup_event():
    logger.info("Research Service starting up...")
    db_session.init_db()

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Research Service shutting down...")
    db_session.dispose_engine()

@app.get("/health")
@limiter.limit(LIMITS["health"])
async def health(request: Request, db: Session = Depends(db_session.get_db)):
    """Service health check."""
    return {
        "status": "healthy",
        "service": "research",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/metrics")
@limiter.limit(LIMITS["health"])
async def metrics(request: Request):
    """Prometheus-style metrics."""
    return metrics_registry.get_metrics_text()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8007)
