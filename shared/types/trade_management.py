from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class SuggestionType(str, Enum):
    MOVE_SL_TO_BE = "MOVE_SL_TO_BE"
    TAKE_PARTIAL_TP1 = "TAKE_PARTIAL_TP1"
    TAKE_PARTIAL_CUSTOM = "TAKE_PARTIAL_CUSTOM"
    HOLD = "HOLD"
    EXIT_BEFORE_NEWS = "EXIT_BEFORE_NEWS"
    CLOSE_END_OF_SESSION = "CLOSE_END_OF_SESSION"
    REDUCE_RISK = "REDUCE_RISK"
    NO_ACTION = "NO_ACTION"


class PositionManagementSuggestion(BaseModel):
    suggestion_id: str | None = None
    created_at_eat: datetime
    ticket_id: int
    broker_trade_id: str
    symbol: str
    side: str
    lots: float
    entry_price: float
    sl: float
    tp1: float | None = None
    tp2: float | None = None
    current_price: float
    current_r: float
    suggestion_type: SuggestionType
    severity: str  # INFO, WARN, CRITICAL
    reasons: list[str]
    expires_at_eat: datetime
    instruction: str  # Human readable instruction like "Move SL to BE: 2034.2"
