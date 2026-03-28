"""
shared/security/middleware.py
----------------------------
Standardized FastAPI middleware and exception handlers for TH-TRADING-SYSTEM.
"""

import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from shared.types.errors import TradingSystemError

logger = logging.getLogger(__name__)

async def trading_system_error_handler(request: Request, exc: TradingSystemError) -> JSONResponse:
    """
    Global exception handler for all TradingSystemError-derived exceptions.
    Returns machine-readable JSON with error_code and severity.
    """
    status_code = 500 if exc.severity in ["ERROR", "CRITICAL"] else 400
    
    # Log the error with context
    log_msg = f"[{exc.error_code}] {exc.message} | severity={exc.severity}"
    if exc.context:
        log_msg += f" | context={exc.context}"
        
    if exc.severity in ["ERROR", "CRITICAL"]:
        logger.error(log_msg, exc_info=True)
    else:
        logger.warning(log_msg)

    return JSONResponse(
        status_code=status_code,
        content={
            "error_code": exc.error_code,
            "message": exc.message,
            "severity": exc.severity,
            "context": exc.context,
        },
    )

def setup_exception_handlers(app) -> None:
    """Register all shared exception handlers to the FastAPI app."""
    app.add_exception_handler(TradingSystemError, trading_system_error_handler)
