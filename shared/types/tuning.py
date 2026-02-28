from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from shared.types.research import SystemMetadata

class Proposal(BaseModel):
    id: str = Field(..., description="Unique ID for this proposal (e.g., PROP-123)")
    title: str = Field(..., description="Short descriptive title of the change")
    target: str = Field(..., description="Category of the target change. EG: guardrails, policy, queue, execution_prep, management")
    proposed_change: str = Field(..., description="A detailed description of the proposed parameter change")
    expected_impact: str = Field(..., description="The hypothesized impact resulting from this change based on research")
    confidence: str = Field(..., description="Confidence level (e.g., HIGH, MEDIUM, LOW)")
    risks: str = Field(..., description="Potential downsides or risks of applying the change")
    rollback_plan: str = Field(..., description="Actionable plan for reverting the change if the impact is negative")
    evidence_refs: List[str] = Field(default_factory=list, description="List of references or metric numbers pointing to evidence")

class TuningProposalReport(BaseModel):
    report_id: str = Field(..., description="Unique ID for this report")
    created_at_eat: datetime = Field(..., description="Timestamp of generation (Africa/Nairobi)")
    date_range: str = Field(..., description="The time window evaluated for this tuning run")
    proposals: List[Proposal] = Field(default_factory=list, description="A list of generated tuning proposals")
    supporting_metrics: Dict[str, Any] = Field(default_factory=dict, description="Raw supporting metric KPIs")
    simulation_links: List[str] = Field(default_factory=list, description="Links/commands to re-run simulations")
    reproducibility: SystemMetadata = Field(..., description="Version and commit information")
