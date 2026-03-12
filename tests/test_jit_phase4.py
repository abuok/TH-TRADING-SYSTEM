import pytest
from datetime import datetime, timedelta, timezone
import pytz
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from shared.database.models import Base, OrderTicket, Packet
from shared.types.enums import TicketState, LockoutState, SessionState
from shared.logic.sessions import get_nairobi_time
from services.orchestration.logic.jit_validator import JITValidator

@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

@pytest.fixture
def validator():
    return JITValidator(lockout_config={
        "max_daily_loss_pct": 2.0,
        "max_consecutive_losses": 3
    })

def create_mock_packets(db, pair="XAUUSD"):
    # Create MarketContextPacket
    ctx = Packet(
        run_id=1,
        packet_type="MarketContextPacket",
        schema_version="1.0.0",
        data={"high_impact_events": []}
    )
    db.add(ctx)
    
    # Create PairFundamentalsPacket
    fund = Packet(
        run_id=1,
        packet_type="PairFundamentalsPacket",
        schema_version="1.0.0",
        data={
            "asset_pair": pair,
            "bias_score": 5.0, # Buy
            "is_invalidated": False,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    )
    db.add(fund)
    db.commit()
    return ctx, fund

def test_jit_confirmation_success(db, validator, monkeypatch):
    ctx, fund = create_mock_packets(db)
    
    # Mock SessionEngine.get_session_state to LDN_OPEN
    monkeypatch.setattr("services.orchestration.logic.jit_validator.SessionEngine.get_session_state", 
                        lambda ts, pair: "LONDON_OPEN")

    ticket = OrderTicket(
        ticket_id="TKT-SUCCESS",
        setup_packet_id=fund.id,
        risk_packet_id=ctx.id, # Mocking IDs
        pair="XAUUSD",
        direction="BUY",
        entry_price=2000.0,
        stop_loss=1990.0,
        take_profit_1=2050.0,
        lot_size=0.1,
        risk_usd=100.0,
        risk_pct=0.5,
        rr_tp1=5.0,
        status=TicketState.PENDING,
        idempotency_key="unique-1",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
    )
    db.add(ticket)
    db.commit()
    
    is_valid, reason, state_hash = validator.validate(db, ticket)
    assert is_valid is True
    assert state_hash != ""

def test_jit_rejection_staleness(db, validator, monkeypatch):
    ctx, fund = create_mock_packets(db)
    
    # Mock session to LDN_OPEN to ensure rejection is due to EXPIRED, not Session
    monkeypatch.setattr("services.orchestration.logic.jit_validator.SessionEngine.get_session_state", 
                        lambda ts, pair: "LONDON_OPEN")

    ticket = OrderTicket(
        ticket_id="TKT-STALE",
        setup_packet_id=fund.id,
        risk_packet_id=ctx.id,
        pair="XAUUSD",
        direction="BUY",
        entry_price=2000.0,
        stop_loss=1990.0,
        take_profit_1=2050.0,
        lot_size=0.1,
        risk_usd=100.0,
        risk_pct=0.5,
        rr_tp1=5.0,
        status=TicketState.PENDING,
        idempotency_key="unique-2",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=10)
    )
    db.add(ticket)
    db.commit()
    
    is_valid, reason, _ = validator.validate(db, ticket)
    assert is_valid is False
    assert "EXPIRED" in reason

def test_jit_rejection_invalidated_bias(db, validator, monkeypatch):
    ctx, fund = create_mock_packets(db)
    # Mutation fix: replace entire dict for SQLAlchemy to track change
    fund.data = {**fund.data, "is_invalidated": True}
    db.commit()
    
    # Mock session to LDN_OPEN to avoid session rejection
    monkeypatch.setattr("services.orchestration.logic.jit_validator.SessionEngine.get_session_state", 
                        lambda ts, pair: "LONDON_OPEN")

    ticket = OrderTicket(
        ticket_id="TKT-INVALID",
        setup_packet_id=fund.id,
        risk_packet_id=ctx.id,
        pair="XAUUSD",
        direction="BUY",
        entry_price=2000.0,
        stop_loss=1990.0,
        take_profit_1=2050.0,
        lot_size=0.1,
        risk_usd=100.0,
        risk_pct=0.5,
        rr_tp1=5.0,
        status=TicketState.PENDING,
        idempotency_key="unique-3",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
    )
    db.add(ticket)
    db.commit()
    
    is_valid, reason, _ = validator.validate(db, ticket)
    assert is_valid is False
    assert "Bias Invalidated" in reason
