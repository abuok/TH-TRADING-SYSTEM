import pytest
from datetime import timedelta
from shared.database.models import OrderTicket, KillSwitch
from shared.logic.execution_logic import PreflightEngine
from shared.logic.sessions import get_nairobi_time
from sqlalchemy.orm import Session
from shared.database.session import get_db


@pytest.fixture
def db_session():
    db = next(get_db())
    yield db


def test_preflight_expiry(db_session: Session):
    engine = PreflightEngine(db_session)

    # Create expired ticket
    ticket = OrderTicket(
        ticket_id="TEST_EXP",
        pair="XAUUSD",
        entry_price=2000.0,
        expires_at=get_nairobi_time() - timedelta(minutes=1),
        setup_packet_id=1,  # Mock
        risk_packet_id=1,
        direction="BUY",
        stop_loss=1990.0,
        take_profit_1=2020.0,
        lot_size=0.1,
        risk_usd=100.0,
        risk_pct=1.0,
        rr_tp1=2.0,
        idempotency_key="EXP_IK",
    )

    checks = engine.run_checks(ticket, current_price=2000.0, current_spread=1.0)
    expiry_check = next(c for c in checks if c.id == "expiry")
    assert expiry_check.status == "FAIL"


def test_preflight_price_tolerance(db_session: Session):
    engine = PreflightEngine(db_session)
    ticket = OrderTicket(
        ticket_id="TEST_PRICE",
        pair="XAUUSD",
        entry_price=2000.0,
        expires_at=get_nairobi_time() + timedelta(minutes=10),
        setup_packet_id=1,
        risk_packet_id=1,
        direction="BUY",
        stop_loss=1990.0,
        take_profit_1=2020.0,
        lot_size=0.1,
        risk_usd=100.0,
        risk_pct=1.0,
        rr_tp1=2.0,
        idempotency_key="PRICE_IK",
    )

    # 0.05% deviation (Pass)
    checks = engine.run_checks(ticket, current_price=2001.0, current_spread=1.0)
    price_check = next(c for c in checks if c.id == "price_deviation")
    assert price_check.status == "PASS"

    # 0.2% deviation (Fail)
    checks = engine.run_checks(ticket, current_price=2004.1, current_spread=1.0)
    price_check = next(c for c in checks if c.id == "price_deviation")
    assert price_check.status == "FAIL"


def test_preflight_kill_switch(db_session: Session):
    engine = PreflightEngine(db_session)
    # Add kill switch
    ks = KillSwitch(switch_type="HALT_ALL", is_active=1)
    db_session.add(ks)
    db_session.commit()

    ticket = OrderTicket(
        ticket_id="TK_KS",
        pair="XAUUSD",
        entry_price=2000.0,
        setup_packet_id=1,
        risk_packet_id=1,
        direction="BUY",
        stop_loss=1990.0,
        take_profit_1=2020.0,
        lot_size=0.1,
        risk_usd=100.0,
        risk_pct=1.0,
        rr_tp1=2.0,
        idempotency_key="KS_IK",
    )

    checks = engine.run_checks(ticket, current_price=2000.0, current_spread=1.0)
    ks_check = next(c for c in checks if c.id == "kill_switch")
    assert ks_check.status == "FAIL"

    # Deactivate
    ks.is_active = 0
    db_session.commit()
    checks = engine.run_checks(ticket, current_price=2000.0, current_spread=1.0)
    assert next(c for c in checks if c.id == "kill_switch").status == "PASS"
