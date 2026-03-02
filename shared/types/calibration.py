from datetime import datetime
from typing import List, Dict, Any
from pydantic import BaseModel, Field
from shared.types.research import SystemMetadata

class Recommendation(BaseModel):
    id: str
    title: str
    change_type: str  # e.g., "threshold", "hard_block", "regime_rule"
    proposed_change: str  # Human readable, e.g., "Increase min_setup_score to 80"
    expected_impact: str  # Expected impact summary, e.g., "Improves E[R] by +0.15R but reduces trades by 20%"
    confidence: str   # "HIGH", "MEDIUM", "LOW"
    rationale: str
    caveats: str

class CalibrationReport(BaseModel):
    report_id: str
    created_at: datetime
    run_ids: List[str]
    pair: str
    timeframe: str
    date_range: str
    
    # Baseline comparison point
    baseline_policy_hash: str
    
    # Selected recommendations logic outputs
    recommendations: List[Recommendation] = Field(default_factory=list)
    
    # Data tables to back up the recommendations
    # Format: dict of dicts e.g., {"Metrics": {"Baseline": ..., "Variant_A": ...}}
    evidence_tables: Dict[str, Any] = Field(default_factory=dict)
    reproducibility: SystemMetadata = Field(..., description="Version and commit information")
