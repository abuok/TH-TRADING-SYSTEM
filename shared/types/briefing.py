"""
BriefingPack schema — Session Briefing Pack types.
All timestamps use Africa/Nairobi (UTC+3).
"""

from datetime import date, datetime
from typing import Any

import pytz
from pydantic import BaseModel, Field

NAIROBI = pytz.timezone("Africa/Nairobi")


def nairobi_now() -> datetime:
    return datetime.now(NAIROBI)


# ──────────────────────────────────────────────
# Sub-models
# ──────────────────────────────────────────────


class StaleWarning(BaseModel):
    field: str
    reason: str  # e.g. "No data found" / "TTL exceeded"


class SystemStatus(BaseModel):
    healthy_services: list[str] = Field(default_factory=list)
    unhealthy_services: list[str] = Field(default_factory=list)
    active_kill_switches: list[str] = Field(default_factory=list)
    last_incident_summary: str | None = None
    last_incident_severity: str | None = None


class MarketContextSummary(BaseModel):
    high_impact_events: list[dict[str, Any]] = Field(default_factory=list)
    no_trade_windows: list[dict[str, Any]] = Field(default_factory=list)
    proxy_snapshots: dict[str, Any] = Field(default_factory=dict)
    is_stale: bool = False


class SetupSummary(BaseModel):
    stage: str
    score: float | None = None
    asset_pair: str
    created_at: datetime | None = None


class TicketSummary(BaseModel):
    ticket_id: str
    status: str  # PENDING/ALLOW/BLOCK
    direction: str
    entry_price: float
    lot_size: float
    rr_tp1: float
    top_reason: str | None = None


class PairOverview(BaseModel):
    pair: str  # e.g. "XAUUSD"
    bias: str = "unknown"  # BULLISH / BEARISH / NEUTRAL / unknown
    bias_score: float | None = None
    bias_invalidation: str = "N/A"
    bias_drivers: list[dict[str, Any]] = Field(default_factory=list)
    key_levels: dict[str, float] = Field(default_factory=dict)
    setup_count_by_stage: dict[str, int] = Field(default_factory=dict)
    top_setups: list[SetupSummary] = Field(default_factory=list)
    latest_ticket: TicketSummary | None = None
    has_stale_data: bool = False
    stale_warnings: list[StaleWarning] = Field(default_factory=list)


class RiskBudget(BaseModel):
    max_daily_loss_pct: float = 2.0
    max_total_loss_pct: float = 5.0
    max_consecutive_losses: int = 3
    allowed_sessions: list[str] = Field(default_factory=lambda: ["LONDON", "NEW YORK"])
    risk_per_trade_usd: float = 100.0
    notes: str | None = None


class OperatorAction(BaseModel):
    priority: str  # HIGH / MEDIUM / LOW
    category: str  # CHECK / AVOID / MONITOR / EXECUTE
    description: str


class DeltaSection(BaseModel):
    """What changed since the previous briefing for the same session."""

    previous_briefing_id: str | None = None
    new_tickets: list[str] = Field(default_factory=list)  # ticket_ids
    resolved_blocks: list[str] = Field(default_factory=list)
    new_setups: list[str] = Field(default_factory=list)  # asset_pairs
    kill_switch_changes: list[str] = Field(default_factory=list)
    incident_count_delta: int = 0
    summary: str = "No previous briefing to compare."


# ──────────────────────────────────────────────
# Root briefing model
# ──────────────────────────────────────────────


class BriefingPack(BaseModel):
    briefing_id: str
    created_at: datetime = Field(default_factory=nairobi_now)
    session_label: str  # ASIA / LONDON / NEW YORK / OUTSIDE
    date: date
    is_delta: bool = False  # True = intraday update; False = pre-session

    system_status: SystemStatus
    market_context: MarketContextSummary
    pair_overviews: list[PairOverview]
    risk_budget: RiskBudget
    operator_actions: list[OperatorAction]
    delta_from_previous: DeltaSection | None = None

    global_warnings: list[str] = Field(
        default_factory=list
    )  # Critical stale / no-data warnings
