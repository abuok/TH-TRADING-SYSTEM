import asyncio
from fastapi import FastAPI, Request
from services.technical.worker import TechnicalWorker
from shared.instrumentation.tracing import init_tracing, instrument_app
from shared.security.middleware import setup_exception_handlers
from shared.security.rate_limiting import LIMITS, limiter, setup_rate_limiting

app = FastAPI(title="PHX Technical Service")

# Initialize v1.3 Core Logic
init_tracing("technical")
setup_rate_limiting(app)
instrument_app(app)
setup_exception_handlers(app)

worker = TechnicalWorker()

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(worker.run())

@app.on_event("shutdown")
async def shutdown_event():
    worker.stop()

@app.get("/health")
@limiter.limit(LIMITS["health"])
async def health_check(request: Request):
    return {
        "status": "healthy",
        "service": "technical",
        "worker_running": getattr(worker, "is_running", False)
    }

@app.get("/setups")
@limiter.limit(LIMITS["dashboard"])
async def get_setups(request: Request):
    """Returns the current state of all active PHX Detectors."""
    return {
        pair: {
            "stage": det.stage.name,
            "score": det.get_score(),
            "bias_direction": det.bias_direction,
            "reason_codes": det.reason_codes[-5:]
        }
        for pair, det in worker.detectors.items()
    }

@app.get("/")
@limiter.limit(LIMITS["default"])
async def root(request: Request):
    return {"message": "PHX Technical Service v1.3 Operational"}
