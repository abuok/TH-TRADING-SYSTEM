from datetime import datetime
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
import hashlib
import json

class SimulatedTrade(BaseModel):
    ticket_id: str
    pair: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: Optional[float] = None
    
    # Outcomes
    status: str = "PENDING"  # PENDING, WIN_TP1, WIN_TP2, LOSS, BE, BLOCKED
    realized_r: float = 0.0
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    
    # Meta
    setup_score: float = 0.0
    bias_score: float = 0.0
    guardrails_status: str = "PASS"
    stage: str = "UNKNOWN"
    block_reason: Optional[str] = None

class CounterfactualConfig(BaseModel):
    min_setup_score: Optional[float] = None
    hard_block_displacement: Optional[bool] = None
    duplicate_suppression_minutes: Optional[int] = None
    use_router: bool = False

class ResearchMetrics(BaseModel):
    total_trades: int = 0
    executed_trades: int = 0
    blocked_trades: int = 0
    win_rate_pct: float = 0.0
    avg_r: float = 0.0
    expectancy_r: float = 0.0
    max_drawdown_r: float = 0.0
    profit_factor: float = 0.0
    total_r: float = 0.0

class ResearchVariant(BaseModel):
    name: str
    config: CounterfactualConfig
    metrics: ResearchMetrics = Field(default_factory=ResearchMetrics)
    trades: List[SimulatedTrade] = Field(default_factory=list)

class ResearchRunResult(BaseModel):
    run_id: str
    pair: str
    start_date: datetime
    end_date: datetime
    timeframes: List[str]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    reproducibility_hash: str = ""
    variants: Dict[str, ResearchVariant] = Field(default_factory=dict)

    def generate_hash(self, git_commit: str = "unknown"):
        data = {
            "pair": self.pair,
            "start": self.start_date.isoformat(),
            "end": self.end_date.isoformat(),
            "git": git_commit,
            "variants": {k: v.config.model_dump() for k, v in self.variants.items()}
        }
        raw = json.dumps(data, sort_keys=True).encode()
        self.reproducibility_hash = hashlib.sha256(raw).hexdigest()[:12]
