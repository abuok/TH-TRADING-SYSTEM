"""
shared/types/incident.py
Pydantic schema for the /incidents/log endpoint request body.
Mirrors the IncidentLog database model fields.
"""

from typing import Any

from pydantic import BaseModel


class IncidentSchema(BaseModel):
    """Request body for logging an incident."""

    severity: str  # INFO, WARNING, ERROR, CRITICAL
    component: str
    error_code: str | None = None
    message: str
    context: dict[str, Any] | None = None
