from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, field_validator


class Candle(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class BasePacket(BaseModel):
    schema_version: str = Field(..., description="SemVer version of the packet schema")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("timestamp")
    @classmethod
    def ensure_timezone_aware(cls, v):
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v


class MarketContextPacket(BasePacket):
    source: str
    asset_pair: str
    price: float
    volume_24h: float
    proxies: Dict[str, Any] = Field(default_factory=dict)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    # First-class event fields (not buried in metrics)
    high_impact_events: List[Dict[str, Any]] = Field(default_factory=list)
    no_trade_windows: List[Dict[str, Any]] = Field(default_factory=list)


class PairBiasPacket(BasePacket):
    asset_pair: str
    bias_score: float = Field(
        ..., ge=-1.0, le=1.0, description="Bullish (+1) to Bearish (-1)"
    )
    signals: List[str]


class TechnicalSetupPacket(BasePacket):
    asset_pair: str
    strategy_name: str
    entry_price: float
    stop_loss: float
    take_profit: float
    timeframe: str
    session_levels: Dict[str, float] = Field(default_factory=dict)


class RiskApprovalPacket(BasePacket):
    request_id: str
    status: str  # ALLOW, ALLOW_WITH_MODS, BLOCK
    is_approved: bool
    risk_score: float
    max_position_size: float
    rr_ratio: float
    approver: str
    reasons: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class DecisionPacket(BasePacket):
    asset_pair: str
    strategy_name: str
    score: float
    bias_score: float
    rr_ratio: float
    risk_status: str
    risk_reasons: List[str]
    entry_price: float
    stop_loss: float
    take_profit: float
    action: str  # e.g., EXECUTE, MONITOR, IGNORE
    is_dry_run: bool = False


class JournalEntryPacket(BasePacket):
    event_type: str
    service_name: str
    message: str
    metadata: Dict[str, str] = Field(default_factory=dict)
    level: str = "INFO"


class AlignmentDecision(BasePacket):
    schema_version: str = "1.0.0"
    asset_pair: str
    is_aligned: bool
    reason_codes: List[str] = Field(default_factory=list)
    eval_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
