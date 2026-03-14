from datetime import datetime

from pydantic import BaseModel, Field


class TradeFillEvent(BaseModel):
    broker_trade_id: str = Field(
        ..., description="Unique ID from the broker (MT5 deal/order ID)"
    )
    symbol: str
    side: str  # BUY, SELL
    lots: float
    price: float
    time_utc: datetime
    time_eat: datetime
    event_type: str  # OPEN, CLOSE, PARTIAL
    sl: float | None = None
    tp: float | None = None
    comment: str | None = None
    magic: int | None = None
    account_id: str
    source: str = "MT5"


class PositionSnapshot(BaseModel):
    position_id: str
    symbol: str
    side: str
    lots: float
    avg_price: float
    floating_pnl: float
    sl: float | None = None
    tp: float | None = None
    updated_at_utc: datetime
    updated_at_eat: datetime
    account_id: str


class TradeFillBatch(BaseModel):
    fills: list[TradeFillEvent]


class PositionSnapshotBatch(BaseModel):
    account_id: str
    snapshots: list[PositionSnapshot]
