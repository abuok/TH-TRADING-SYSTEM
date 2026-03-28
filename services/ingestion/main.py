"""
services/ingestion/main.py
Ingestion Service — wires CalendarProvider and ProxyProvider from env vars.

Provider selection:
  CALENDAR_PROVIDER=mock|forexfactory   (default: mock)
  PROXY_PROVIDER=mock|real              (default: mock)
"""

import asyncio
import logging

from fastapi import BackgroundTasks, Depends, FastAPI, Request

import shared.database.session as db_session
from shared.database.models import IncidentLog
from shared.instrumentation.tracing import init_tracing, instrument_app
from shared.messaging.event_bus import EventBus
from shared.providers.calendar import get_calendar_provider
from shared.providers.proxy import get_proxy_provider
from shared.security.middleware import setup_exception_handlers
from shared.security.rate_limiting import LIMITS, limiter, setup_rate_limiting, rate_limit
from shared.security.auth import verify_auth
from shared.config.settings import settings
from shared.types.errors import TradingSystemError
from shared.types.packets import MarketContextPacket

logger = logging.getLogger("IngestionService")

app = FastAPI(title="Ingestion Service")

# Initialize v1.3 Core Logic
init_tracing("ingestion")
setup_rate_limiting(app)
instrument_app(app)
setup_exception_handlers(app)

event_bus = EventBus()

# Singletons — created at startup so env vars are already loaded
_proxy_provider = None
_calendar_provider = None


def _get_providers():
    global _proxy_provider, _calendar_provider
    if _proxy_provider is None:
        _proxy_provider = get_proxy_provider()
    if _calendar_provider is None:
        _calendar_provider = get_calendar_provider()
    return _proxy_provider, _calendar_provider


def _log_incident(severity: str, component: str, message: str) -> None:
    """Write an incident to the DB and log it."""
    logger.error("[INCIDENT][%s] %s — %s", severity, component, message)
    try:
        with db_session.get_transactional_db() as db:
            db.add(IncidentLog(severity=severity, component=component, message=message))
    except Exception as exc:
        logger.error("Failed to persist incident: %s", exc)


async def ingest_calendar() -> None:
    """Background loop: fetch calendar and proxy data, emit MarketContextPacket."""
    while True:
        proxy_provider, calendar_provider = _get_providers()
        try:
            events = calendar_provider.fetch_events()
            windows = calendar_provider.get_no_trade_windows(events)

            try:
                proxies = proxy_provider.get_snapshots()
            except NotImplementedError as exc:
                _log_incident(
                    "ERROR",
                    "IngestionService",
                    f"ProxyProvider not implemented — failing closed: {exc}",
                )
                proxies = {}

            packet = MarketContextPacket(
                schema_version="1.0.1",
                source=f"Calendar={type(calendar_provider).__name__},"
                f"Proxy={type(proxy_provider).__name__}",
                asset_pair="ALL",
                price=0.0,
                volume_24h=0.0,
                proxies=proxies,
                metrics={
                    "high_impact_events_count": len(events),
                    "no_trade_windows_count": len(windows),
                },
                # First-class event fields
                high_impact_events=events,
                no_trade_windows=windows,
            )
            event_bus.publish("market_context", packet.model_dump(mode="json"))
            logger.info(
                "Ingestion: emitted MarketContextPacket — %d events, %d no-trade windows.",
                len(events),
                len(windows),
            )

        except Exception as exc:  # noqa: BLE001
            _log_incident(
                "ERROR",
                "IngestionService",
                f"Unhandled ingestion error: {exc}",
            )
            logger.error("Ingestion loop error: %s", exc, exc_info=True)

        await asyncio.sleep(3600)


@app.on_event("startup")
async def startup_event():
    db_session.init_db()
    _get_providers()  # Validate env vars early — crash fast if misconfigured
    asyncio.create_task(ingest_calendar())


@app.get("/health")
@limiter.limit(LIMITS["health"])
async def health_check(request: Request):
    try:
        return {
            "status": "healthy",
            "service": "ingestion",
            "proxy_provider": type(_proxy_provider).__name__
            if _proxy_provider
            else "uninitialised",
            "calendar_provider": type(_calendar_provider).__name__
            if _calendar_provider
            else "uninitialised",
        }
    except Exception as exc:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=503, content={"status": "unhealthy", "error": str(exc)}
        )


@app.post("/trigger")
@rate_limit("ingestion_trigger")
async def trigger_ingestion(background_tasks: BackgroundTasks, _=Depends(verify_auth)):
    """Manually trigger a calendar refresh."""
    background_tasks.add_task(ingest_calendar)
    return {"message": "Ingestion triggered"}
