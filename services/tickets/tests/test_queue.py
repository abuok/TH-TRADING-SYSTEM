from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.database.models import Base, OrderTicket
from shared.types.trading import SkipReasonEnum, TicketOutcomeEnum
from services.tickets.queue_logic import approve_ticket, skip_ticket, close_ticket, auto_expire_tickets

# --- In-Memory DB Setup ---
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

def create_mock_ticket(db, ticket_id="TKT-1", status="IN_REVIEW", offset_mins=15):
    """Helper to inject a mock ticket."""
    now = datetime.now(timezone.utc)
    t = OrderTicket(
        ticket_id=ticket_id,
        setup_packet_id=1,
        risk_packet_id=1,
        pair="XAUUSD",
        direction="BUY",
        entry_price=1900.0,
        stop_loss=1890.0,
        take_profit_1=1920.0,
        lot_size=0.1,
        risk_usd=100.0,
        risk_pct=1.0,
        rr_tp1=2.0,
        status=status,
        idempotency_key=f"hash_{ticket_id}",
        expires_at=now + timedelta(minutes=offset_mins),
        created_at=now
    )
    db.add(t)
    db.commit()
    return t

# --- Tests ---

def test_approve_ticket(db_session):
    create_mock_ticket(db_session, "TKT-A")
    ticket = approve_ticket(db_session, "TKT-A")
    
    assert ticket.status == "APPROVED"
    assert ticket.review_decision == "APPROVE"
    assert ticket.reviewed_at is not None

def test_cannot_approve_wrong_status(db_session):
    create_mock_ticket(db_session, "TKT-B", status="APPROVED")
    
    with pytest.raises(ValueError, match="Ticket must be IN_REVIEW"):
        approve_ticket(db_session, "TKT-B")

def test_skip_ticket(db_session):
    create_mock_ticket(db_session, "TKT-C")
    ticket = skip_ticket(db_session, "TKT-C", SkipReasonEnum.NEWS_WINDOW, notes="NFP coming")
    
    assert ticket.status == "SKIPPED"
    assert ticket.review_decision == "SKIP"
    assert ticket.skip_reason == "NEWS_WINDOW"
    assert ticket.notes == "NFP coming"
    assert ticket.reviewed_at is not None

def test_close_ticket(db_session):
    # Must be APPROVED to close
    create_mock_ticket(db_session, "TKT-D", status="APPROVED")
    ticket = close_ticket(db_session, "TKT-D", outcome=TicketOutcomeEnum.WIN, exit_price=1920.5, realized_r=2.05)
    
    assert ticket.status == "CLOSED"
    assert ticket.manual_outcome_label == "WIN"
    assert ticket.manual_exit_price == 1920.5
    assert ticket.manual_outcome_r == 2.05
    assert ticket.closed_at is not None

def test_auto_expire_tickets(db_session):
    # Valid ticket: +15 mins
    create_mock_ticket(db_session, "TKT-VALID", status="IN_REVIEW", offset_mins=15)
    # Stale ticket: -5 mins (should expire)
    create_mock_ticket(db_session, "TKT-STALE", status="IN_REVIEW", offset_mins=-5)
    # Already approved ticket (should ignore even if past time)
    create_mock_ticket(db_session, "TKT-APP", status="APPROVED", offset_mins=-5)
    
    expired_count = auto_expire_tickets(db_session)
    assert expired_count == 1
    
    t_valid = db_session.query(OrderTicket).filter_by(ticket_id="TKT-VALID").first()
    t_stale = db_session.query(OrderTicket).filter_by(ticket_id="TKT-STALE").first()
    t_app = db_session.query(OrderTicket).filter_by(ticket_id="TKT-APP").first()
    
    assert t_valid.status == "IN_REVIEW"
    assert t_stale.status == "EXPIRED"
    assert t_stale.reviewed_at is not None
    assert t_app.status == "APPROVED"
