from fastapi import FastAPI
from shared.logic.risk import RiskEngine
from shared.messaging.event_bus import EventBus
import asyncio

app = FastAPI(title="Risk Service")
event_bus = EventBus()
# Placeholder config
risk_engine = RiskEngine({
    "max_daily_loss": 30.0,
    "max_total_loss": 100.0,
    "max_consecutive_losses": 2,
    "min_rr_threshold": 2.0,
    "lot_size_limit": 0.1,
    "account_balance": 1000.0
})

@app.on_event("startup")
async def startup_event():
    # Placeholder: In a real system, this would subscribe to 'technical_setups'
    # and 'market_context' to evaluate setups in real-time.
    pass

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "risk"}
