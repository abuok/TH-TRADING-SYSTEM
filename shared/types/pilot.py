from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
from datetime import date

class PairStats(BaseModel):
    pair: str
    trades_executed: int
    win_rate_pct: float
    realized_r: float
    missed_r: float
    max_drawdown_r: float

class PilotSessionRecord(BaseModel):
    session_id: str = Field(..., description="Unique ID for this session (e.g., PILOT-2026-02-28)")
    date: str = Field(..., description="Date of the session YYYY-MM-DD")
    session_label: str = Field(..., description="e.g., Session 1 of 10")
    
    # Granular details
    pair_stats: List[PairStats] = Field(default_factory=list)
    
    # Gateway metrics
    process_metrics: Dict[str, Any] = Field(default_factory=dict, description="Ticket approvals, expirations, overrides")
    performance_metrics: Dict[str, Any] = Field(default_factory=dict, description="R, WR, Drawdown")
    reliability_metrics: Dict[str, Any] = Field(default_factory=dict, description="Quote freshness, staleness")
    policy_metrics: Dict[str, Any] = Field(default_factory=dict, description="Policy routing stats")
    
    pass_fail: str = Field(..., description="PASS or FAIL based on gateway thresholds")
    notes: List[str] = Field(default_factory=list, description="Reasons for failure or interesting notes")

class PilotScorecard(BaseModel):
    scorecard_id: str = Field(..., description="Unique ID for this scorecard")
    date_range: str = Field(..., description="Evaluated window (e.g., 2026-02-14 to 2026-02-28)")
    
    sessions: List[PilotSessionRecord] = Field(default_factory=list)
    
    aggregates: Dict[str, Any] = Field(default_factory=dict, description="Aggregated metric values across the rolling window")
    pass_fail_summary: str = Field(..., description="Overall Pilot PASS/FAIL")
    
    next_week_plan: List[str] = Field(default_factory=list, description="Advisory action items and tuning recommendations")
