from pydantic import BaseModel, Field
from enum import Enum

class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"

class RiskDecision(str, Enum):
    APPROVE = "APPROVE"
    BLOCK = "BLOCK"

class SignalPacket(BaseModel):
    id: str
    symbol: str  # XAUUSD, GBPJPY
    direction: Direction
    entry: float
    sl: float
    tp: float
    timestamp: str  # EAT (Africa/Nairobi)
    strategy: str

class ScorePacket(BaseModel):
    signal_id: str
    confidence_score: float = Field(..., ge=0, le=100)
    metadata: dict = Field(default_factory=dict)  # ATR, RSI, etc.

class RiskPacket(BaseModel):
    signal_id: str
    decision: RiskDecision
    reason: str
    max_drawdown_check: bool
    session_check: bool

class ForensicJournalEntry(BaseModel):
    timestamp: str
    signal: SignalPacket
    score: ScorePacket
    risk: RiskPacket
    final_status: str
