from datetime import datetime

from pydantic import BaseModel, Field


class HindsightOutcome(BaseModel):
    ticket_id: str
    computed_at: datetime
    outcome_label: str = Field(..., description="WIN, LOSS, BE, or NONE")
    realized_r: float
    first_hit: str = Field(..., description="SL, TP1, TP2, or NONE")
    time_to_hit_min: int | None = None
    notes: str | None = None
    policy_hash: str | None = None
