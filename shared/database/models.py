from sqlalchemy import (
    Column,
    Integer,
    String,
    JSON,
    DateTime,
    ForeignKey,
    Float,
    Boolean,
    Date,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime, timezone

Base = declarative_base()


class Run(Base):
    __tablename__ = "runs"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String, unique=True, index=True, nullable=False)
    started_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    status = Column(String, default="running")  # e.g., running, completed, failed

    packets = relationship("Packet", back_populates="run")


class Packet(Base):
    __tablename__ = "packets"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("runs.id"), nullable=False)
    packet_type = Column(
        String, index=True, nullable=False
    )  # e.g., MarketContextPacket
    schema_version = Column(String, nullable=False)
    data = Column(JSON, nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    run = relationship("Run", back_populates="packets")


class KillSwitch(Base):
    __tablename__ = "kill_switches"

    id = Column(Integer, primary_key=True, index=True)
    switch_type = Column(
        String, nullable=False
    )  # HALT_ALL, HALT_PAIR, HALT_SERVICE, HALT_EXECUTION
    target = Column(String, nullable=True)  # e.g., BTCUSD or IngestionService
    is_active = Column(Integer, default=1)  # 1 for active, 0 for inactive
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class IncidentLog(Base):
    __tablename__ = "incident_logs"

    id = Column(Integer, primary_key=True, index=True)
    severity = Column(
        String, index=True, nullable=False
    )  # INFO, WARNING, ERROR, CRITICAL
    component = Column(String, index=True, nullable=False)
    error_code = Column(String, index=True)
    message = Column(String, nullable=False)
    context = Column(JSON)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class OrderTicket(Base):
    __tablename__ = "order_tickets"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(String, unique=True, index=True, nullable=False)
    setup_packet_id = Column(Integer, ForeignKey("packets.id"), nullable=False)
    risk_packet_id = Column(Integer, ForeignKey("packets.id"), nullable=False)
    pair = Column(String, nullable=False)
    direction = Column(String, nullable=False)  # BUY, SELL
    entry_type = Column(String, default="MARKET")  # MARKET, LIMIT
    entry_price = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    take_profit_1 = Column(Float, nullable=False)
    take_profit_2 = Column(Float, nullable=True)
    lot_size = Column(Float, nullable=False)
    risk_usd = Column(Float, nullable=False)
    risk_pct = Column(Float, nullable=False)
    rr_tp1 = Column(Float, nullable=False)
    rr_tp2 = Column(Float, nullable=True)
    status = Column(String, default="PENDING")  # PENDING, TAKEN, NOT_TAKEN, BLOCKED
    block_reason = Column(String, nullable=True)
    idempotency_key = Column(String, unique=True, index=True, nullable=False)
    jit_validation_hash = Column(String, nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    active_policy_name = Column(String, nullable=True)
    active_policy_hash = Column(String, nullable=True)

    expires_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    executed_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    review_decision = Column(String, nullable=True)  # APPROVE, SKIP
    skip_reason = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    manual_entry_price = Column(Float, nullable=True)
    manual_exit_price = Column(Float, nullable=True)
    manual_outcome_r = Column(Float, nullable=True)
    manual_outcome_label = Column(String, nullable=True)  # WIN, LOSS, BE
    manual_screenshot_ref = Column(String, nullable=True)

    alignment_score = Column(Integer, nullable=True)  # 0–100 quality metric
    is_aligned = Column(Boolean, default=False)
    alignment_summary = Column(JSON, nullable=True)  # top issues list

    hindsight_status = Column(String, default="PENDING")  # PENDING, DONE, UNAVAILABLE
    hindsight_outcome_label = Column(String, nullable=True)  # WIN, LOSS, BE, NONE
    hindsight_realized_r = Column(Float, nullable=True)

    setup_packet = relationship("Packet", foreign_keys=[setup_packet_id])
    risk_packet = relationship("Packet", foreign_keys=[risk_packet_id])


class SessionBriefing(Base):
    __tablename__ = "session_briefings"

    id = Column(Integer, primary_key=True, index=True)
    briefing_id = Column(String, unique=True, index=True, nullable=False)
    session_label = Column(String, nullable=False)  # ASIA, LONDON, NEW YORK, OUTSIDE
    date = Column(Date, nullable=False)
    is_delta = Column(Boolean, default=False)  # False = pre-session, True = intraday
    html_path = Column(
        String, nullable=True
    )  # relative path under artifacts/briefings/
    data = Column(JSON, nullable=False)  # full BriefingPack JSON
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class AlignmentLog(Base):
    __tablename__ = "alignment_logs"

    id = Column(Integer, primary_key=True, index=True)
    setup_packet_id = Column(Integer, ForeignKey("packets.id"), nullable=True)
    ticket_id = Column(String, nullable=True)  # filled when ticket is created
    pair = Column(String, nullable=False)
    alignment_score = Column(Integer, nullable=False)
    is_aligned = Column(Boolean, default=False)
    primary_block_reason = Column(Text, nullable=True)
    alignment_version = Column(String, default="1.0.0")
    result_json = Column(JSON, nullable=False)  # full AlignmentDecision JSON
    policy_name = Column(String, nullable=True)
    policy_hash = Column(String, nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class HindsightOutcomeLog(Base):
    __tablename__ = "hindsight_outcome_logs"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(
        String, ForeignKey("order_tickets.ticket_id"), nullable=False, index=True
    )
    computed_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    outcome_label = Column(String, nullable=False)  # WIN, LOSS, BE, NONE
    realized_r = Column(Float, nullable=False)
    first_hit = Column(String, nullable=False)  # SL, TP1, TP2, NONE
    time_to_hit_min = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    policy_hash = Column(String, nullable=True)

    ticket = relationship("OrderTicket", foreign_keys=[ticket_id])


class PolicySelectionLog(Base):
    __tablename__ = "policy_selection_logs"

    id = Column(Integer, primary_key=True, index=True)
    pair = Column(String, nullable=False, index=True)
    policy_name = Column(String, nullable=False)
    policy_hash = Column(String, nullable=False)
    reasons = Column(JSON, nullable=False)
    regime_signals = Column(JSON, nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class ActionItem(Base):
    __tablename__ = "action_items"
    id = Column(Integer, primary_key=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    title = Column(String)
    severity = Column(String)  # INFO, WARNING, ERROR, CRITICAL
    source = Column(String)  # ops, weekly, calibration
    evidence_links = Column(JSON)  # List of strings/URLs
    status = Column(String, default="OPEN")  # OPEN, DONE
    notes = Column(Text)


class OpsReportLog(Base):
    __tablename__ = "ops_report_logs"
    id = Column(Integer, primary_key=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    report_type = Column(String)  # daily, weekly
    report_data = Column(JSON)  # Full report as JSON
    html_path = Column(String)  # Path to the generated HTML


class ExecutionPrepLog(Base):
    __tablename__ = "execution_prep_logs"
    id = Column(Integer, primary_key=True)
    prep_id = Column(String, unique=True, index=True)
    ticket_id = Column(String, ForeignKey("order_tickets.ticket_id"), nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    expires_at = Column(DateTime(timezone=True), nullable=False)
    data = Column(JSON, nullable=False)  # Full ExecutionPrepSchema
    status = Column(String, default="ACTIVE")  # ACTIVE, EXPIRED, OVERRIDDEN
    override_reason = Column(Text, nullable=True)

    ticket = relationship("OrderTicket", foreign_keys=[ticket_id])


class LiveQuote(Base):
    __tablename__ = "live_quotes"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, unique=True, index=True, nullable=False)
    bid = Column(Float, nullable=False)
    ask = Column(Float, nullable=False)
    spread = Column(Float, nullable=False)
    raw_timestamp = Column(String, nullable=True)  # UTC from MT5
    captured_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class SymbolSpec(Base):
    __tablename__ = "symbol_specs"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, unique=True, index=True, nullable=False)
    contract_size = Column(Float, nullable=False)
    tick_size = Column(Float, nullable=False)
    tick_value = Column(Float, nullable=False)
    pip_size = Column(Float, nullable=False)
    min_lot = Column(Float, default=0.01)
    lot_step = Column(Float, default=0.01)
    captured_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class TradeFillLog(Base):
    __tablename__ = "trade_fills_log"

    id = Column(Integer, primary_key=True, index=True)
    broker_trade_id = Column(String, index=True, nullable=False)
    symbol = Column(String, nullable=False)
    side = Column(String, nullable=False)
    lots = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    time_utc = Column(DateTime(timezone=True), nullable=False)
    time_eat = Column(DateTime(timezone=True), nullable=False)
    event_type = Column(String, nullable=False)  # OPEN, CLOSE, PARTIAL
    sl = Column(Float, nullable=True)
    tp = Column(Float, nullable=True)
    comment = Column(Text, nullable=True)
    magic = Column(Integer, nullable=True)
    account_id = Column(String, nullable=False)
    source = Column(String, default="MT5")
    captured_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint(
            "broker_trade_id", "event_type", "time_utc", name="_broker_fill_uc"
        ),
    )


class PositionSnapshot(Base):
    __tablename__ = "position_snapshots"

    id = Column(Integer, primary_key=True)
    position_id = Column(String, unique=True, index=True, nullable=False)
    symbol = Column(String, nullable=False)
    side = Column(String, nullable=False)
    lots = Column(Float, nullable=False)
    avg_price = Column(Float, nullable=False)
    floating_pnl = Column(Float, nullable=False)
    sl = Column(Float, nullable=True)
    tp = Column(Float, nullable=True)
    updated_at_utc = Column(DateTime(timezone=True), nullable=False)
    updated_at_eat = Column(DateTime(timezone=True), nullable=False)
    account_id = Column(String, nullable=False)
    captured_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class TicketTradeLink(Base):
    __tablename__ = "ticket_trade_link"

    id = Column(Integer, primary_key=True)
    ticket_id = Column(
        String, ForeignKey("order_tickets.ticket_id"), nullable=False, index=True
    )
    broker_trade_id = Column(String, nullable=False, index=True)
    match_method = Column(String, nullable=False)  # COMMENT, HEURISTIC
    match_score = Column(Float, default=1.0)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    ticket = relationship("OrderTicket", foreign_keys=[ticket_id])


class JournalLog(Base):
    __tablename__ = "journal_logs"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(
        String, ForeignKey("order_tickets.ticket_id"), nullable=True, index=True
    )
    event_type = Column(
        String, nullable=False, index=True
    )  # TRADE_OPENED, TRADE_PARTIAL, TRADE_CLOSED, etc.
    message = Column(Text, nullable=False)
    data = Column(
        JSON, nullable=True
    )  # Extra metadata like broker_trade_id, price, lots
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    ticket = relationship("OrderTicket", foreign_keys=[ticket_id])


class ManagementSuggestionLog(Base):
    __tablename__ = "management_suggestions_log"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(
        String, ForeignKey("order_tickets.ticket_id"), nullable=False, index=True
    )
    broker_trade_id = Column(String, nullable=False, index=True)
    suggestion_type = Column(String, nullable=False, index=True)  # MOVE_SL_TO_BE, etc.
    severity = Column(String, nullable=False)  # INFO, WARN, CRITICAL
    data = Column(JSON, nullable=False)  # Full suggestion details
    time_bucket = Column(
        String, nullable=False, index=True
    )  # e.g., "S1-2026-02-28-18" for dedup
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    expires_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "ticket_id",
            "suggestion_type",
            "time_bucket",
            name="_ticket_suggestion_bucket_uc",
        ),
    )

    ticket = relationship("OrderTicket", foreign_keys=[ticket_id])


class TuningProposalLog(Base):
    __tablename__ = "tuning_proposals_log"

    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    status = Column(String, default="OPEN", index=True)  # OPEN, ACCEPTED, REJECTED
    reviewer_notes = Column(Text, nullable=True)
    data = Column(JSON, nullable=False)  # Full TuningProposalReport JSON


class PilotSessionLog(Base):
    __tablename__ = "pilot_sessions_log"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, unique=True, index=True, nullable=False)
    date = Column(Date, index=True, nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    pass_fail = Column(String, index=True)  # PASS or FAIL
    data = Column(JSON, nullable=False)  # Full PilotSessionRecord JSON


class PilotScorecardLog(Base):
    __tablename__ = "pilot_scorecards_log"

    id = Column(Integer, primary_key=True, index=True)
    scorecard_id = Column(String, unique=True, index=True, nullable=False)
    date_range = Column(String, nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    pass_fail = Column(String, index=True)  # PASS or FAIL
    data = Column(JSON, nullable=False)  # Full PilotScorecard JSON


class QuoteStaleLog(Base):
    __tablename__ = "quote_stale_logs"
    id = Column(Integer, primary_key=True)
    symbol = Column(String, index=True, nullable=False)
    stale_duration_seconds = Column(Float, nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

class DisciplineLockout(Base):
    __tablename__ = "discipline_lockouts"

    id = Column(Integer, primary_key=True, index=True)
    reason = Column(String, nullable=False)
    triggered_by_rule = Column(String, nullable=False)
    triggered_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    reset_type = Column(String, nullable=False)  # CRON vs MANUAL
    is_resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    operator_id = Column(String, nullable=True)
