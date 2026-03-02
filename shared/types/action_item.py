from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class ActionItemSchema(BaseModel):
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    title: str
    severity: str
    source: str
    evidence_links: List[str] = []
    status: str = "OPEN"
    notes: Optional[str] = None

    class Config:
        from_attributes = True
