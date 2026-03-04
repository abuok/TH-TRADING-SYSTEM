import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.database.models import (
    Base,
    OrderTicket,
    PositionSnapshot,
    TicketTradeLink,
    ManagementSuggestionLog,
    Packet,
    Run,
)
from shared.logic.trade_management_engine import run_management_cycle
from shared.providers.price_quote import (
    MockPriceQuoteProvider,
    set_price_quote_provider,
)

# Setup in-memory SQLite for testing
engine = create_engine("sqlite:///:memory:")
SessionLocal = sessionmaker(bind=engine)


@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)
    # Reset global provider so it doesn't leak into other test files
    set_price_quote_provider(None)


def test_move_sl_to_be_suggestion(db, monkeypatch):
    import shared.logic.trade_management_engine as tme

    # Pin Nairobi time to 14:00 EAT (London session, well clear of 00:30-01:00 session-close window)
    def mock_get_nairobi_time():
        from pytz import timezone as py_tz

        eat = py_tz("Africa/Nairobi")
        return datetime(2026, 3, 4, 14, 0, tzinfo=eat)

    monkeypatch.setattr(tme, "get_nairobi_time", mock_get_nairobi_time)

    # 1. Setup Mock Provider
    mock_quotes = MockPriceQuoteProvider()
    set_price_quote_provider(mock_quotes)

    # 2. Seed Data
    run = Run(run_id="R1")
    db.add(run)
    db.flush()

    p1 = Packet(
        run_id=run.id,
        packet_type="SetupPacket",
        schema_version="2.0",
        data={"pair": "EURUSD"},
    )
    db.add(p1)
    db.flush()

    # Ticket at 1.00000, SL at 0.99900 (10 pips risk)
    ticket = OrderTicket(
        ticket_id="T1",
        setup_packet_id=p1.id,
        risk_packet_id=p1.id,
        pair="EURUSD",
        direction="BUY",
        entry_price=1.00000,
        stop_loss=0.99900,
        take_profit_1=1.00200,
        lot_size=0.1,
        risk_usd=100.0,
        risk_pct=1.0,
        rr_tp1=2.0,
        idempotency_key="T1_KEY",
        status="APPROVED",
    )
    db.add(ticket)
    db.flush()

    now = datetime.now(timezone.utc)
    # Position linked to T1
    pos = PositionSnapshot(
        position_id=12345,
        symbol="EURUSD",
        side="BUY",
        lots=0.1,
        avg_price=1.00000,
        sl=0.99900,
        tp=1.00200,
        floating_pnl=0.0,
        updated_at_utc=now,
        updated_at_eat=now.replace(
            tzinfo=None
        ),  # Mock EAT as naive for simplicity in sqlite
        account_id="TEST_ACC",
    )
    db.add(pos)

    link = TicketTradeLink(ticket_id="T1", broker_trade_id=12345, match_method="MANUAL")
    db.add(link)
    db.commit()

    # 3. Scenario: Price is at 1.00110 (which is 1.1R)
    mock_quotes.set_quote("EURUSD", 1.00110, 1.00111)

    # 4. Run Cycle
    run_management_cycle(db)

    # 5. Assert suggestion created
    sug = db.query(ManagementSuggestionLog).first()
    assert sug is not None
    assert sug.suggestion_type == "MOVE_SL_TO_BE"
    assert sug.data["current_r"] >= 1.0
    assert "Move SL to Entry" in sug.data["instruction"]


def test_tp1_partial_suggestion(db):
    # 1. Setup Mock Provider
    mock_quotes = MockPriceQuoteProvider()
    set_price_quote_provider(mock_quotes)

    # 2. Seed Data
    run = Run(run_id="R2")
    db.add(run)
    db.flush()

    p2 = Packet(
        run_id=run.id,
        packet_type="SetupPacket",
        schema_version="2.0",
        data={"pair": "GBPUSD"},
    )
    db.add(p2)
    db.flush()

    ticket = OrderTicket(
        ticket_id="T2",
        setup_packet_id=p2.id,
        risk_packet_id=p2.id,
        pair="GBPUSD",
        direction="BUY",
        entry_price=1.30000,
        stop_loss=1.29900,
        take_profit_1=1.30200,  # TP1 at 2.0R
        lot_size=0.2,
        risk_usd=200.0,
        risk_pct=1.0,
        rr_tp1=2.0,
        idempotency_key="T2_KEY",
        status="APPROVED",
    )
    db.add(ticket)
    db.flush()

    now = datetime.now(timezone.utc)
    pos = PositionSnapshot(
        position_id=67890,
        symbol="GBPUSD",
        side="BUY",
        lots=0.2,
        avg_price=1.30000,
        sl=1.29900,
        tp=1.30400,
        floating_pnl=0.0,
        updated_at_utc=now,
        updated_at_eat=now.replace(tzinfo=None),
        account_id="TEST_ACC",
    )
    db.add(pos)

    link = TicketTradeLink(ticket_id="T2", broker_trade_id=67890, match_method="MANUAL")
    db.add(link)
    db.commit()

    # 3. Scenario: Price is at 1.30200 (Hit TP1)
    mock_quotes.set_quote("GBPUSD", 1.30200, 1.30201)

    # 4. Run Cycle
    run_management_cycle(db)

    # 5. Assert
    sug = (
        db.query(ManagementSuggestionLog)
        .filter(ManagementSuggestionLog.suggestion_type == "TAKE_PARTIAL_TP1")
        .first()
    )
    assert sug is not None
    assert "0.10 lots" in sug.data["instruction"]


def test_killswitch_suggestion(db):
    from shared.database.models import KillSwitch

    mock_quotes = MockPriceQuoteProvider()
    set_price_quote_provider(mock_quotes)

    ks = KillSwitch(switch_type="GLOBAL", is_active=1)
    db.add(ks)

    run = Run(run_id="R3")
    db.add(run)
    db.flush()

    p3 = Packet(
        run_id=run.id,
        packet_type="SetupPacket",
        schema_version="2.0",
        data={"pair": "USDJPY"},
    )
    db.add(p3)
    db.flush()

    ticket = OrderTicket(
        ticket_id="T3",
        setup_packet_id=p3.id,
        risk_packet_id=p3.id,
        pair="USDJPY",
        direction="SELL",
        entry_price=150.00,
        stop_loss=150.50,
        take_profit_1=149.00,
        lot_size=0.5,
        risk_usd=500.0,
        risk_pct=1.0,
        rr_tp1=2.0,
        idempotency_key="T3_KEY",
        status="APPROVED",
    )
    db.add(ticket)
    db.flush()

    now = datetime.now(timezone.utc)
    pos = PositionSnapshot(
        position_id=11111,
        symbol="USDJPY",
        side="SELL",
        lots=0.5,
        avg_price=150.00,
        sl=150.50,
        tp=149.00,
        floating_pnl=0.0,
        updated_at_utc=now,
        updated_at_eat=now.replace(tzinfo=None),
        account_id="TEST_ACC",
    )
    db.add(pos)

    link = TicketTradeLink(ticket_id="T3", broker_trade_id=11111, match_method="MANUAL")
    db.add(link)
    db.commit()

    mock_quotes.set_quote("USDJPY", 149.90, 149.91)  # Small profit

    run_management_cycle(db)

    sug = (
        db.query(ManagementSuggestionLog)
        .filter(ManagementSuggestionLog.ticket_id == str(ticket.id))
        .first()
    )
    assert sug is not None
    assert sug.suggestion_type == "NO_ACTION"
    assert sug.severity == "CRITICAL"
    assert "Kill Switch Active" in sug.data["reasons"][0]


def test_end_of_session_suggestion(db, monkeypatch):
    import shared.logic.trade_management_engine as tme

    # Mock time to 00:45 EAT
    def mock_get_nairobi_time():
        from pytz import timezone as py_tz

        eat = py_tz("Africa/Nairobi")
        dt = datetime(2026, 2, 28, 0, 45, tzinfo=eat)
        return dt

    monkeypatch.setattr(tme, "get_nairobi_time", mock_get_nairobi_time)

    mock_quotes = MockPriceQuoteProvider()
    set_price_quote_provider(mock_quotes)

    run = Run(run_id="R4")
    db.add(run)
    db.flush()

    p = Packet(
        run_id=run.id,
        packet_type="SetupPacket",
        schema_version="2.0",
        data={"pair": "AUDUSD"},
    )
    db.add(p)
    db.flush()

    ticket = OrderTicket(
        ticket_id="T4",
        setup_packet_id=p.id,
        risk_packet_id=p.id,
        pair="AUDUSD",
        direction="BUY",
        entry_price=0.6500,
        stop_loss=0.6400,
        take_profit_1=0.6600,
        lot_size=1.0,
        risk_usd=100.0,
        risk_pct=1.0,
        rr_tp1=1.0,
        idempotency_key="T4_KEY",
        status="APPROVED",
    )
    db.add(ticket)
    db.flush()

    pos = PositionSnapshot(
        position_id=22222,
        symbol="AUDUSD",
        side="BUY",
        lots=1.0,
        avg_price=0.6500,
        sl=0.6400,
        tp=0.6600,
        floating_pnl=0.0,
        updated_at_utc=datetime.now(timezone.utc),
        updated_at_eat=datetime.now(),
        account_id="TEST_ACC",
    )
    db.add(pos)

    link = TicketTradeLink(ticket_id="T4", broker_trade_id=22222, match_method="MANUAL")
    db.add(link)
    db.commit()

    mock_quotes.set_quote("AUDUSD", 0.6510, 0.6511)

    run_management_cycle(db)

    sug = (
        db.query(ManagementSuggestionLog)
        .filter(ManagementSuggestionLog.ticket_id == str(ticket.id))
        .first()
    )
    assert sug is not None
    assert sug.suggestion_type == "CLOSE_END_OF_SESSION"
    assert sug.severity == "WARN"


def test_policy_risk_off_suggestion(db, monkeypatch):
    import shared.logic.trade_management_engine as tme

    # Pin Nairobi time to 14:00 EAT (London session, well clear of 00:30-01:00 session-close window)
    def mock_get_nairobi_time():
        from pytz import timezone as py_tz

        eat = py_tz("Africa/Nairobi")
        return datetime(2026, 3, 4, 14, 0, tzinfo=eat)

    monkeypatch.setattr(tme, "get_nairobi_time", mock_get_nairobi_time)

    from shared.database.models import PolicySelectionLog

    mock_quotes = MockPriceQuoteProvider()
    set_price_quote_provider(mock_quotes)

    # 2. Add Active RISK_OFF policy
    policy = PolicySelectionLog(
        pair="NZDUSD",
        policy_name="RISK_OFF",
        policy_hash="ABC",
        reasons=[],
        regime_signals={},
    )
    db.add(policy)

    run = Run(run_id="R5")
    db.add(run)
    db.flush()

    p = Packet(
        run_id=run.id,
        packet_type="SetupPacket",
        schema_version="2.0",
        data={"pair": "NZDUSD"},
    )
    db.add(p)
    db.flush()

    ticket = OrderTicket(
        ticket_id="T5",
        setup_packet_id=p.id,
        risk_packet_id=p.id,
        pair="NZDUSD",
        direction="BUY",
        entry_price=0.6000,
        stop_loss=0.5900,
        take_profit_1=0.6200,
        lot_size=0.2,
        risk_usd=100.0,
        risk_pct=1.0,
        rr_tp1=2.0,
        idempotency_key="T5_KEY",
        status="APPROVED",
    )
    db.add(ticket)
    db.flush()

    pos = PositionSnapshot(
        position_id=33333,
        symbol="NZDUSD",
        side="BUY",
        lots=0.2,
        avg_price=0.6000,
        sl=0.5900,
        tp=0.6200,
        floating_pnl=0.0,
        updated_at_utc=datetime.now(timezone.utc),
        updated_at_eat=datetime.now(),
        account_id="TEST_ACC",
    )
    db.add(pos)

    link = TicketTradeLink(ticket_id="T5", broker_trade_id=33333, match_method="MANUAL")
    db.add(link)
    db.commit()

    # 0.6R (>= 0.5R) profit
    mock_quotes.set_quote("NZDUSD", 0.6060, 0.6061)

    run_management_cycle(db)

    sug = (
        db.query(ManagementSuggestionLog)
        .filter(ManagementSuggestionLog.ticket_id == str(ticket.id))
        .first()
    )
    assert sug is not None
    assert sug.suggestion_type == "REDUCE_RISK"
    assert sug.severity == "WARN"
