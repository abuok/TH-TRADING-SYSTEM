from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.database.models import Base, OrderTicket
from shared.logic.trading_logic import generate_order_ticket
from shared.types.packets import RiskApprovalPacket, TechnicalSetupPacket

# In-memory DB for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_generate_ticket_success(db):
    setup = TechnicalSetupPacket(
        schema_version="1.0.0",
        asset_pair="XAUUSD",
        strategy_name="PHX",
        entry_price=2000.0,
        stop_loss=1990.0,
        take_profit=2030.0,
        timeframe="1H",
        timestamp=datetime.now(timezone.utc),
    )
    risk = RiskApprovalPacket(
        schema_version="1.0.0",
        request_id="req-123",
        status="ALLOW",
        is_approved=True,
        risk_score=10.0,
        max_position_size=1.0,
        rr_ratio=3.0,
        approver="RiskEngine",
        timestamp=datetime.now(timezone.utc),
    )

    from shared.types.packets import AlignmentDecision

    alignment = AlignmentDecision(asset_pair="XAUUSD", is_aligned=True, reason_codes=[])
    ticket = generate_order_ticket(setup, risk, db, risk_usd=100.0, alignment=alignment)

    assert ticket.pair == "XAUUSD"
    assert ticket.direction == "BUY"
    # Lot sizing for XAUUSD: Risk 100 / (Dist 10 * Factor 100) = 0.1
    assert ticket.lot_size == 0.1
    assert ticket.rr_tp1 == 3.0
    assert ticket.status == "PENDING"
    assert ticket.ticket_id.startswith("TKT-")


def test_generate_ticket_blocked(db):
    setup = TechnicalSetupPacket(
        schema_version="1.0.0",
        asset_pair="EURUSD",
        strategy_name="PHX",
        entry_price=1.1000,
        stop_loss=1.0900,
        take_profit=1.1200,
        timeframe="1H",
        timestamp=datetime.now(timezone.utc),
    )
    risk = RiskApprovalPacket(
        schema_version="1.0.0",
        request_id="req-blo",
        status="BLOCK",
        is_approved=False,
        risk_score=90.0,
        max_position_size=0.0,
        rr_ratio=2.0,
        approver="RiskEngine",
        reasons=["Max daily loss reached"],
        timestamp=datetime.now(timezone.utc),
    )

    ticket = generate_order_ticket(setup, risk, db)

    assert ticket.status == "BLOCKED"
    assert "Max daily loss reached" in ticket.block_reason


def test_ticket_idempotency(db):
    setup = TechnicalSetupPacket(
        schema_version="1.0.0",
        asset_pair="XAUUSD",
        strategy_name="PHX",
        entry_price=2000.0,
        stop_loss=1995.0,
        take_profit=2010.0,
        timeframe="1H",
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    risk = RiskApprovalPacket(
        schema_version="1.0.0",
        request_id="req-456",
        status="ALLOW",
        is_approved=True,
        risk_score=5.0,
        max_position_size=2.0,
        rr_ratio=2.0,
        approver="RiskEngine",
        timestamp=datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc),
    )

    t1 = generate_order_ticket(setup, risk, db)
    t2 = generate_order_ticket(setup, risk, db)

    assert t1.id == t2.id
    assert db.query(OrderTicket).count() == 1


def test_platform_formatters():
    from shared.types.trading import OrderTicketSchema

    ticket = OrderTicketSchema(
        ticket_id="TKT-TEST",
        setup_packet_id=1,
        risk_packet_id=2,
        pair="XAUUSD",
        direction="BUY",
        entry_price=2000.0,
        stop_loss=1990.0,
        take_profit_1=2030.0,
        lot_size=0.1,
        risk_usd=100.0,
        risk_pct=0.5,
        rr_tp1=3.0,
        idempotency_key="key",
    )

    mt5 = ticket.to_mt5_note()
    assert "MT5 TRADE PLAN" in mt5
    assert "Size: 0.10 Lots" in mt5

    ctrader = ticket.to_ctrader_note()
    assert "cTrader Order" in ctrader
    assert "Volume: 0.10 Lots" in ctrader
