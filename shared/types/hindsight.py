from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class HindsightOutcome(BaseModel):
    ticket_id: str
    computed_at: datetime
    outcome_label: str = Field(..., description="WIN, LOSS, BE, or NONE")
    realized_r: float
    first_hit: str = Field(..., description="SL, TP1, TP2, or NONE")
    time_to_hit_min: Optional[int] = None
    notes: Optional[str] = None
    policy_hash: Optional[str] = None
