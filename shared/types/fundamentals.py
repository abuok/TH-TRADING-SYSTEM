from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

# ──────────────────────────────────────────────
# Sub-models
# ──────────────────────────────────────────────

class BulletItem(BaseModel):
    category: str        # e.g., "YIELDS", "USD", "RISK_SENTIMENT"
    text: str            # e.g., "US10Y rising (+0.05%)"
    impact: int          # -1, 0, or 1 indicating bearish/neutral/bullish component score

class ProxySnapshot(BaseModel):
    symbol: str
    current_value: float
    previous_value: Optional[float] = None
    delta_pct: Optional[float] = None

# ──────────────────────────────────────────────
# Packet Models
# ──────────────────────────────────────────────

class MarketMoversPacket(BaseModel):
    schema_version: str = "1.0.0"
    packet_type: str = "MarketMoversPacket"
    created_at: datetime
    ttl_seconds: int = 1800  # Default 30 minutes
    
    # Core proxy data that drives models
    proxies: Dict[str, ProxySnapshot] = Field(default_factory=dict)
    
    # Qualitative / event-driven context
    sentiment_flags: List[str] = Field(default_factory=list) # e.g. ["RISK_OFF", "HAWKISH_FED"]
    sources: List[str] = Field(default_factory=list) # "MockProxyProvider", "EconomicCalendar"

class PairFundamentalsPacket(BaseModel):
    schema_version: str = "1.0.0"
    packet_type: str = "PairFundamentalsPacket"
    asset_pair: str
    created_at: datetime
    ttl_seconds: int = 3600 # Pair bias valid longer, e.g., 1 hour or session
    
    bias_score: float        # -5.0 to +5.0 scale
    bias_label: str          # "BULLISH", "BEARISH", "NEUTRAL"
    confidence_label: str    # "HIGH", "MEDIUM", "LOW"
    
    # Explainable drivers for dashboard and briefings
    drivers: List[BulletItem] = Field(default_factory=list)
    invalidation_criteria: str # What proxy movement would flip the bias
    
    sources: List[str] = Field(default_factory=list) # "DeterministicModel_V1"
