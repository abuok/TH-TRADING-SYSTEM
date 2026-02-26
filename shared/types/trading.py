from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field

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
    take_profit_2: Optional[float] = None
    lot_size: float
    risk_usd: float
    risk_pct: float
    rr_tp1: float
    rr_tp2: Optional[float] = None
    status: str = "PENDING"
    block_reason: Optional[str] = None
    idempotency_key: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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
            lines.append(f"Take Profit 2: {self.take_profit_2} (RR: {self.rr_tp2:.2f}R)")
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
