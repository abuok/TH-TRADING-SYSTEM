"""
services/bridge/main.py
Live Data Bridge Service — Ingests real-time quotes and symbol specs from MT5.
"""
import os
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, Header, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from shared.database.models import LiveQuote, SymbolSpec, IncidentLog
import shared.database.session as db_session
from shared.logic.sessions import get_nairobi_time

logger = logging.getLogger("BridgeService")

app = FastAPI(title="Live Data Bridge")

# Security key from env
BRIDGE_SECRET = os.getenv("BRIDGE_SECRET", "change-me-in-prod")

class QuotePayload(BaseModel):
    symbol: str
    bid: float
    ask: float
    ts_utc: Optional[str] = None

class SpecPayload(BaseModel):
    symbol: str
    contract_size: float
    tick_size: float
    tick_value: float
    pip_size: float
    min_lot: float = 0.01
    lot_step: float = 0.01

def verify_secret(x_bridge_secret: str = Header(...)):
    if x_bridge_secret != BRIDGE_SECRET:
        raise HTTPException(status_code=403, detail="Invalid bridge secret")

@app.post("/bridge/quote")
async def post_quote(payload: QuotePayload, db: Session = Depends(db_session.get_db), authenticated: bool = Depends(verify_secret)):
    """
    Ingest a live quote. Idempotent: ignore if price hasn't changed.
    """
    try:
        # Calculate spread
        spread = round(payload.ask - payload.bid, 5)
        
        # Check existing for idempotency
        existing = db.query(LiveQuote).filter(LiveQuote.symbol == payload.symbol).first()
        if existing:
            if existing.bid == payload.bid and existing.ask == payload.ask:
                return {"status": "ignored", "reason": "no change"}
            
            existing.bid = payload.bid
            existing.ask = payload.ask
            existing.spread = spread
            existing.raw_timestamp = payload.ts_utc
            existing.captured_at = datetime.now(timezone.utc)
        else:
            new_quote = LiveQuote(
                symbol=payload.symbol,
                bid=payload.bid,
                ask=payload.ask,
                spread=spread,
                raw_timestamp=payload.ts_utc
            )
            db.add(new_quote)
        
        db.commit()
        return {"status": "success", "symbol": payload.symbol, "spread": spread}
    except Exception as e:
        logger.error(f"Error posting quote: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/bridge/spec")
async def post_spec(payload: SpecPayload, db: Session = Depends(db_session.get_db), authenticated: bool = Depends(verify_secret)):
    """
    Ingest symbol specifications (contract size, tick info).
    """
    try:
        existing = db.query(SymbolSpec).filter(SymbolSpec.symbol == payload.symbol).first()
        if existing:
            existing.contract_size = payload.contract_size
            existing.tick_size = payload.tick_size
            existing.tick_value = payload.tick_value
            existing.pip_size = payload.pip_size
            existing.min_lot = payload.min_lot
            existing.lot_step = payload.lot_step
            existing.captured_at = datetime.now(timezone.utc)
        else:
            new_spec = SymbolSpec(
                symbol=payload.symbol,
                contract_size=payload.contract_size,
                tick_size=payload.tick_size,
                tick_value=payload.tick_value,
                pip_size=payload.pip_size,
                min_lot=payload.min_lot,
                lot_step=payload.lot_step
            )
            db.add(new_spec)
        
        db.commit()
        return {"status": "success", "symbol": payload.symbol}
    except Exception as e:
        logger.error(f"Error posting spec: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "bridge"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)
