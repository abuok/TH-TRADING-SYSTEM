from datetime import datetime

from pydantic import BaseModel


class ActionItemSchema(BaseModel):
    id: int | None = None
    created_at: datetime | None = None
    title: str
    severity: str
    source: str
    evidence_links: list[str] = []
    status: str = "OPEN"
    notes: str | None = None

    class Config:
        from_attributes = True
