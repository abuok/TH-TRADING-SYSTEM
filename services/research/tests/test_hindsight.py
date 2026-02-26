import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.database.models import Base, OrderTicket, HindsightOutcomeLog
from shared.types.packets import Candle
from shared.types.trading import SkipReasonEnum
from services.research.hindsight import process_ticket_hindsight, walk_forward

engine = create_engine('sqlite:///:memory:')
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)

def create_mock_ticket(db, ticket_id="HS-1", is_long=True, status="SKIPPED"):
    t = OrderTicket(
        ticket_id=ticket_id,
        setup_packet_id=1,
        risk_packet_id=1,
        pair="XAUUSD",
        direction="BUY" if is_long else "SELL",
        entry_type="MARKET",
        entry_price=100.0,
        stop_loss=90.0 if is_long else 110.0,
        take_profit_1=120.0 if is_long else 80.0,
        take_profit_2=None,
        lot_size=0.1,
        risk_usd=100.0,
        risk_pct=1.0,
        rr_tp1=2.0,
        status=status,
        skip_reason="NEWS_WINDOW",
        idempotency_key=f"hash_{ticket_id}",
        created_at=datetime.now(timezone.utc),
        hindsight_status="PENDING"
    )
    db.add(t)
    db.commit()
    return t

# --- Unit Tests ---

def test_long_win_tp1(db_session):
    ticket = create_mock_ticket(db_session, is_long=True)
    # Candles never hit 90 (SL), go straight to 120 (TP1)
    candles = [
        Candle(timestamp=datetime.now(), open=100, high=105, low=95, close=100, volume=0),
        Candle(timestamp=datetime.now(), open=100, high=125, low=100, close=120, volume=0)
    ]
    
    outcome = process_ticket_hindsight(db_session, ticket.ticket_id, candles)
    
    assert outcome is not None
    assert outcome.outcome_label == "WIN"
    assert outcome.first_hit == "TP1"
    assert outcome.realized_r == 2.0  # (120 - 100) / 10
    assert outcome.time_to_hit_min == 1
    
    # DB checked
    assert ticket.hindsight_status == "DONE"
    
def test_long_loss_sl(db_session):
    ticket = create_mock_ticket(db_session, is_long=True)
    candles = [
        Candle(timestamp=datetime.now(), open=100, high=105, low=85, close=90, volume=0)
    ]
    outcome = process_ticket_hindsight(db_session, ticket.ticket_id, candles)
    
    assert outcome.outcome_label == "LOSS"
    assert outcome.first_hit == "SL"
    assert outcome.realized_r == -1.0
    
def test_long_tie_breaker(db_session):
    ticket = create_mock_ticket(db_session, is_long=True)
    # Candle hits both TP (120) and SL (90) inside the same tick. Conservative rule defaults to SL hit first.
    candles = [
        Candle(timestamp=datetime.now(), open=100, high=130, low=80, close=100, volume=0)
    ]
    outcome = process_ticket_hindsight(db_session, ticket.ticket_id, candles)
    
    assert outcome.outcome_label == "LOSS"
    assert outcome.first_hit == "SL"

def test_long_break_even(db_session):
    ticket = create_mock_ticket(db_session, is_long=True)
    # 1. Travel +1R (110) moving stops to Break Even (100)
    # 2. Reverse back to 95. Since Stop is at 100, it hits BE instead of full Loss.
    candles = [
        Candle(timestamp=datetime.now(), open=100, high=115, low=100, close=110, volume=0),
        Candle(timestamp=datetime.now(), open=110, high=110, low=95, close=95, volume=0)
    ]
    outcome = process_ticket_hindsight(db_session, ticket.ticket_id, candles)
    
    assert outcome.outcome_label == "BE"
    assert outcome.first_hit == "SL" # The stop loss triggered, it was just physically at the Entry.
    assert outcome.realized_r == 0.0

def test_short_win_tp1(db_session):
    ticket = create_mock_ticket(db_session, ticket_id="HS-2", is_long=False)
    # Entry 100, SL 110, TP 80
    candles = [
        Candle(timestamp=datetime.now(), open=100, high=105, low=95, close=100, volume=0),
        Candle(timestamp=datetime.now(), open=100, high=100, low=75, close=80, volume=0)
    ]
    outcome = process_ticket_hindsight(db_session, ticket.ticket_id, candles)
    
    assert outcome.outcome_label == "WIN"
    assert outcome.first_hit == "TP1"
    assert outcome.realized_r == 2.0  # (100 - 80) / 10

def test_short_break_even(db_session):
    ticket = create_mock_ticket(db_session, ticket_id="HS-3", is_long=False)
    # Entry 100, SL 110, TP 80
    # Travels 1R into profit (down to 90), then reverses up to 110. SL moved to 100.
    candles = [
        Candle(timestamp=datetime.now(), open=100, high=100, low=85, close=90, volume=0),
        Candle(timestamp=datetime.now(), open=90, high=115, low=90, close=110, volume=0)
    ]
    outcome = process_ticket_hindsight(db_session, ticket.ticket_id, candles)
    
    assert outcome.outcome_label == "BE"
    assert outcome.realized_r == 0.0

def test_expiration_horizon_none(db_session):
    ticket = create_mock_ticket(db_session, ticket_id="HS-EX", is_long=True)
    # Dingle around Entry, never hitting SL or TP, until max_candles runs out.
    candles = [
        Candle(timestamp=datetime.now(), open=100, high=105, low=95, close=100, volume=0)
    ] * 1500 # Over the 1440 default limit
    
    outcome = process_ticket_hindsight(db_session, ticket.ticket_id, candles)
    assert outcome.outcome_label == "NONE"
    assert outcome.first_hit == "NONE"
    assert outcome.realized_r == 0.0
    assert outcome.time_to_hit_min == 1440
