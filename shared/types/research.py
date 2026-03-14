import hashlib
import json
import os
from datetime import datetime

from pydantic import BaseModel, Field


class SystemMetadata(BaseModel):
    version: str = Field(..., description="System version (e.g., 1.0.0)")
    git_commit: str = Field(..., description="Short git commit hash")
    guardrails_version: str = Field(
        ..., description="Version of the guardrails policy used"
    )
    policy_hash: str = Field(..., description="Hash of the active policy configuration")
    dataset_hash: str | None = Field(
        None, description="Hash of the input dataset if applicable"
    )


class SimulatedTrade(BaseModel):
    ticket_id: str
    pair: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float | None = None

    # Outcomes
    status: str = "PENDING"  # PENDING, WIN_TP1, WIN_TP2, LOSS, BE, BLOCKED
    realized_r: float = 0.0
    exit_price: float | None = None
    exit_time: datetime | None = None

    # Meta
    setup_score: float = 0.0
    bias_score: float = 0.0
    guardrails_status: str = "PASS"
    stage: str = "UNKNOWN"
    block_reason: str | None = None


class CounterfactualConfig(BaseModel):
    min_setup_score: float | None = None
    hard_block_displacement: bool | None = None
    duplicate_suppression_minutes: int | None = None
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
    trades: list[SimulatedTrade] = Field(default_factory=list)


class ResearchRunResult(BaseModel):
    run_id: str
    pair: str
    start_date: datetime
    end_date: datetime
    timeframes: list[str]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    reproducibility_hash: str = ""
    guardrails_version: str = ""
    dataset_hash: str = ""
    variants: dict[str, ResearchVariant] = Field(default_factory=dict)

    def generate_hash(
        self,
        git_commit: str = "unknown",
        guardrails_version: str = "unknown",
        dataset_path: str = "",
    ) -> None:
        """Compute a deterministic fingerprint covering all inputs that affect research results."""
        # Hash the dataset file itself for byte-level reproducibility
        dataset_hash = ""
        if dataset_path and os.path.exists(dataset_path):
            h = hashlib.sha256()
            with open(dataset_path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            dataset_hash = h.hexdigest()[:12]

        data = {
            "pair": self.pair,
            "start": self.start_date.isoformat(),
            "end": self.end_date.isoformat(),
            "git": git_commit,
            "guardrails_version": guardrails_version,
            "dataset_hash": dataset_hash,
            "variants": {k: v.config.model_dump() for k, v in self.variants.items()},
        }
        raw = json.dumps(data, sort_keys=True).encode()
        self.reproducibility_hash = hashlib.sha256(raw).hexdigest()[:12]
        self.guardrails_version = guardrails_version
        self.dataset_hash = dataset_hash
