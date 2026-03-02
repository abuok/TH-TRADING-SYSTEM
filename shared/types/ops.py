from datetime import datetime
from typing import List, Dict, Any
from pydantic import BaseModel, Field


class SkipStats(BaseModel):
    count: int = 0
    top_reasons: List[str] = Field(default_factory=list)


class HindsightSummary(BaseModel):
    total_skipped: int = 0
    total_expired: int = 0
    avg_missed_r: float = 0.0
    missed_winners_count: int = 0


class DailyOpsReport(BaseModel):
    report_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Health & Incidents
    health_status: str = "HEALTHY"
    incident_count: int = 0

    # Policies
    active_policies: Dict[str, str] = Field(default_factory=dict)  # Pair -> PolicyName
    policy_switches_24h: int = 0

    # Market Context
    high_impact_events: List[Dict[str, Any]] = Field(default_factory=list)
    no_trade_windows: List[Dict[str, Any]] = Field(default_factory=list)

    # Queue Stats
    queue_approvals: int = 0
    queue_skips: int = 0
    queue_expires: int = 0
    top_skip_reasons: List[str] = Field(default_factory=list)

    # Hindsight
    hindsight_yesterday: HindsightSummary = Field(default_factory=HindsightSummary)

    # Checklist
    checklist_do: List[str] = Field(default_factory=list)
    checklist_dont: List[str] = Field(default_factory=list)


class WeeklyReviewReport(BaseModel):
    report_id: str
    start_date: datetime
    end_date: datetime

    # Performance
    total_realized_r: float = 0.0
    total_missed_r: float = 0.0
    win_rate_pct: float = 0.0

    # Discipline
    rule_violations_count: int = 0
    avg_guardrails_score: float = 0.0

    # Decision Quality
    skipped_winners: int = 0
    skipped_losers: int = 0
    approved_winners: int = 0
    approved_losers: int = 0

    # Regimes
    performance_by_policy: Dict[str, float] = Field(default_factory=dict)
    performance_by_sentiment: Dict[str, float] = Field(default_factory=dict)

    # Insights
    top_insights: List[str] = Field(default_factory=list)
    top_mistakes: List[str] = Field(default_factory=list)
    recommended_tweaks: List[str] = Field(default_factory=list)

    # Action Items
    created_action_items: List[str] = Field(default_factory=list)
