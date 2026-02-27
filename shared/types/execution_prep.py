from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class PreflightCheck(BaseModel):
    id: str
    name: str
    status: str # PASS, WARN, FAIL
    details: str

class PlatformFormats(BaseModel):
    mt5_text: str
    ctrader_text: str
    json_data: Dict[str, Any]

class ExecutionPrepSchema(BaseModel):
    prep_id: str
    ticket_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime
    platform_formats: PlatformFormats
    preflight_checks: List[PreflightCheck]
    price_tolerance_pct: float
    override_required: bool = False
    override_reason: Optional[str] = None
    status: str = "ACTIVE" # ACTIVE, EXPIRED, OVERRIDDEN, EXECUTED
