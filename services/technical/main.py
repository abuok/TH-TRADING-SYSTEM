from fastapi import FastAPI, Request

from shared.instrumentation.tracing import init_tracing, instrument_app
from shared.security.middleware import setup_exception_handlers
from shared.security.rate_limiting import LIMITS, limiter, setup_rate_limiting

app = FastAPI(title="Technical Service")

# Initialize v1.3 Core Logic
init_tracing("technical")
setup_rate_limiting(app)
instrument_app(app)
setup_exception_handlers(app)


@app.get("/health")
@limiter.limit(LIMITS["health"])
async def health_check(request: Request):
    return {"status": "healthy", "service": "technical"}


@app.get("/")
@limiter.limit(LIMITS["default"])
async def root(request: Request):
    return {"message": "Hello World from Technical Service"}
