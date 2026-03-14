from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class SkipReasonEnum(str, Enum):
    NEWS_WINDOW = "NEWS_WINDOW"
    STALE = "STALE"
    SPREAD_TOO_HIGH = "SPREAD_TOO_HIGH"
    LOW_SCORE = "LOW_SCORE"
    FUNDAMENTALS_CONFLICT = "FUNDAMENTALS_CONFLICT"
    ALREADY_MOVED = "ALREADY_MOVED"
    MAX_RISK_REACHED = "MAX_RISK_REACHED"
    PERSONAL_RULE = "PERSONAL_RULE"


class TicketOutcomeEnum(str, Enum):
    WIN = "WIN"
    LOSS = "LOSS"
    BE = "BE"


class OrderTicketSchema(BaseModel):
    ticket_id: str
    setup_packet_id: int
    risk_packet_id: int
    pair: str
    direction: str
    entry_type: str = "MARKET"
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float | None = None
    lot_size: float
    risk_usd: float
    risk_pct: float
    rr_tp1: float
    rr_tp2: float | None = None
    status: str = "PENDING"
    block_reason: str | None = None
    idempotency_key: str
    jit_validation_hash: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None
    reviewed_at: datetime | None = None
    closed_at: datetime | None = None
    review_decision: str | None = None
    skip_reason: SkipReasonEnum | None = None
    notes: str | None = None
    manual_entry_price: float | None = None
    manual_exit_price: float | None = None
    manual_outcome_r: float | None = None
    manual_outcome_label: TicketOutcomeEnum | None = None
    manual_screenshot_ref: str | None = None

    # Mission E: Bridge Data
    executed_at: datetime | None = None
    broker_trade_id: str | None = None
    realized_r: float | None = None

    def to_mt5_note(self) -> str:
        """Formats the ticket as a plain text note for MT5."""
        lines = [
            f"--- MT5 TRADE PLAN: {self.pair} ---",
            f"Direction: {self.direction}",
            f"Entry: {self.entry_price} ({self.entry_type})",
            f"Stop Loss: {self.stop_loss}",
            f"Take Profit 1: {self.take_profit_1} (RR: {self.rr_tp1:.2f}R)",
        ]
        if self.take_profit_2:
            lines.append(
                f"Take Profit 2: {self.take_profit_2} (RR: {self.rr_tp2:.2f}R)"
            )
        lines.append(f"Size: {self.lot_size:.2f} Lots")
        lines.append(f"Risk: ${self.risk_usd:.2f} ({self.risk_pct:.2f}%)")
        if self.status == "BLOCKED":
            lines.insert(1, f"!! BLOCKED: {self.block_reason} !!")
        return "\n".join(lines)

    def to_ctrader_note(self) -> str:
        """Formats the ticket as a plain text note for cTrader."""
        lines = [
            f"cTrader Order: {self.pair} | {self.direction}",
            f"Price: {self.entry_price} | Type: {self.entry_type}",
            f"SL: {self.stop_loss} | TP1: {self.take_profit_1}",
        ]
        if self.take_profit_2:
            lines.append(f"TP2: {self.take_profit_2}")
        lines.append(f"Volume: {self.lot_size:.2f} Lots")
        lines.append(f"Risk: {self.risk_pct:.2f}% / ${self.risk_usd:.2f}")
        if self.status == "BLOCKED":
            lines.insert(0, f"STATUS: BLOCKED - {self.block_reason}")
        return "\n".join(lines)
