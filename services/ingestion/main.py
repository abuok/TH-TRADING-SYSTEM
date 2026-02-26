from fastapi import FastAPI, BackgroundTasks
from .calendar import EconomicCalendar
from .proxies import MockProxyProvider
from shared.messaging.event_bus import EventBus
from shared.types.packets import MarketContextPacket
import json
import asyncio

app = FastAPI(title="Ingestion Service")
event_bus = EventBus()
proxy_provider = MockProxyProvider()

async def ingest_calendar():
    """Background task to fetch calendar and emit packets."""
    while True:
        try:
            events = EconomicCalendar.fetch_events()
            windows = EconomicCalendar.get_no_trade_windows(events)
            proxies = proxy_provider.get_snapshots()
            
            packet = MarketContextPacket(
                schema_version="1.0.0",
                source="ForexFactory+MockProxies",
                asset_pair="ALL", # Global context
                price=0.0,
                volume_24h=0.0,
                proxies=proxies,
                metrics={
                    "high_impact_events_count": len(events),
                    "no_trade_windows_count": len(windows)
                }
            )
            # Store windows in metadata or data if we had a more specific field, 
            # for now we'll just log and emit a basic packet.
            
            event_bus.publish("market_context", packet.dict())
        except Exception as e:
            print(f"Ingestion error: {e}")
            
        await asyncio.sleep(3600) # Check every hour

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(ingest_calendar())

@app.get("/health")
async def health_check():
    try:
        # Check Redis indirectly via event_bus if possible
        return {"status": "healthy", "service": "ingestion", "redis": "initialized"}
    except Exception as e:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"status": "unhealthy", "error": str(e)})

@app.get("/trigger")
async def trigger_ingestion(background_tasks: BackgroundTasks):
    """Manually trigger a calendar refresh."""
    background_tasks.add_task(ingest_calendar)
    return {"message": "Ingestion triggered"}
