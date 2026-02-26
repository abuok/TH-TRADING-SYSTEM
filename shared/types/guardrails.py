"""
shared/types/guardrails.py
GuardrailsResult schema for PHX v2 strategy rule enforcement.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import pytz

NAIROBI = pytz.timezone("Africa/Nairobi")
GUARDRAILS_VERSION = "2.0.0"


class EvidenceRef(BaseModel):
    """Machine-readable reference to a candle, level, packet, or metric."""
    ref_type: str              # "candle_ts" | "level" | "packet_id" | "metric"
    key: str                   # e.g. "sweep_candle", "choch_level", "setup_packet_id"
    value: Any                 # actual value (timestamp string, float, int, str)
    description: Optional[str] = None


class RuleCheck(BaseModel):
    """Result for a single guardrail rule evaluation."""
    id: str                    # e.g. "GR-S01"
    name: str                  # Human-readable rule name
    status: str                # "PASS" | "FAIL" | "WARN"
    details: str               # Why this status was assigned
    evidence_refs: List[EvidenceRef] = Field(default_factory=list)
    is_mandatory: bool = True  # FAIL on mandatory rule → hard_block
    deduction: int = 0         # Score deducted (0=PASS, 5=WARN, 20=FAIL)


class GuardrailsResult(BaseModel):
    """Aggregate guardrails evaluation result for a setup."""
    guardrails_version: str = GUARDRAILS_VERSION
    setup_packet_id: Optional[int] = None
    pair: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(NAIROBI)
    )

    rule_checks: List[RuleCheck]
    discipline_score: int = Field(ge=0, le=100, description="0–100 composite score")
    hard_block: bool = False
    primary_block_reason: Optional[str] = None

    # Convenience aggregates
    @property
    def pass_count(self) -> int:
        return sum(1 for r in self.rule_checks if r.status == "PASS")

    @property
    def warn_count(self) -> int:
        return sum(1 for r in self.rule_checks if r.status == "WARN")

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.rule_checks if r.status == "FAIL")

    @property
    def top_issues(self) -> List[RuleCheck]:
        """Top 3 FAIL/WARN items sorted by severity."""
        ranked = sorted(
            [r for r in self.rule_checks if r.status in ("FAIL", "WARN")],
            key=lambda r: (0 if r.status == "FAIL" else 1, r.id)
        )
        return ranked[:3]

    def brief_summary(self) -> str:
        """One-line summary for briefings and notifications."""
        emoji = "🔴" if self.hard_block else ("🟡" if self.warn_count else "🟢")
        return (
            f"{emoji} Score {self.discipline_score}/100 | "
            f"PASS:{self.pass_count} WARN:{self.warn_count} FAIL:{self.fail_count}"
            + (f" | BLOCK: {self.primary_block_reason}" if self.hard_block else "")
        )
