from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)

from shared.database.models import Base


class JournalSetup(Base):
    __tablename__ = "journal_setups"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(String, unique=True, index=True)
    asset_pair = Column(String, index=True)
    strategy_name = Column(String)
    entry_price = Column(Float)
    stop_loss = Column(Float)
    take_profit = Column(Float)
    timeframe = Column(String)
    setup_score = Column(Float)
    score_label = Column(String)  # A+, B, C
    status = Column(String, default="PENDING")  # PENDING, TAKEN, MISSED
    timestamp = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    metadata_json = Column(JSON, default={})


class JournalRiskDecision(Base):
    __tablename__ = "journal_risk_decisions"

    id = Column(Integer, primary_key=True, index=True)
    setup_id = Column(Integer, ForeignKey("journal_setups.id"))
    request_id = Column(String, index=True)
    status = Column(String)  # ALLOW, BLOCK
    is_approved = Column(Boolean)
    rr_ratio = Column(Float)
    reasons = Column(JSON, default=[])
    timestamp = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class JournalTradeOutcome(Base):
    __tablename__ = "journal_trade_outcomes"

    id = Column(Integer, primary_key=True, index=True)
    setup_id = Column(Integer, ForeignKey("journal_setups.id"))
    is_win = Column(Boolean)
    r_multiple = Column(Float)
    pnl = Column(Float)
    timestamp = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    notes = Column(String, nullable=True)


class JournalTicket(Base):
    __tablename__ = "journal_tickets"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(String, index=True)
    setup_id = Column(Integer, ForeignKey("journal_setups.id"), nullable=True)
    risk_decision_id = Column(
        Integer, ForeignKey("journal_risk_decisions.id"), nullable=True
    )
    status = Column(String)
    timestamp = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    plan_snapshot = Column(JSON)


class JournalTicketTransition(Base):
    __tablename__ = "journal_ticket_transitions"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(String, index=True)
    transition_type = Column(String, index=True)  # APPROVED, SKIPPED, EXPIRED, CLOSED
    timestamp = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    details_json = Column(JSON, default={})
