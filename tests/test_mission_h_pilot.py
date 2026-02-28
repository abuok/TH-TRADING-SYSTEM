import pytest
from datetime import date, timedelta, datetime, timezone
from sqlalchemy.orm import Session
from shared.database.models import (
    OrderTicket, ExecutionPrepLog, PilotSessionLog, PilotScorecardLog, TuningProposalLog
)
from services.research.pilot import build_pilot_scorecard, fetch_session_metrics
from shared.logic.sessions import get_nairobi_time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from shared.database.models import Base

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

def create_mock_ticket(ticket_id, pair, status, created_at, realized_r=None):
    return OrderTicket(
        ticket_id=ticket_id,
        setup_packet_id=1,
        risk_packet_id=1,
        pair=pair,
        direction="BUY",
        entry_price=1.0,
        stop_loss=0.9,
        take_profit_1=1.1,
        lot_size=0.1,
        risk_usd=100.0,
        risk_pct=1.0,
        rr_tp1=1.0,
        idempotency_key=f"IK-{ticket_id}",
        status=status,
        manual_outcome_r=realized_r,
        created_at=created_at
    )

def test_pilot_metrics_aggregation(db):
    # Seed data for a passing session
    today = date(2026, 2, 28)
    dt_today = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
    
    # Passing ticket
    t1 = create_mock_ticket("PILOT-T1", "EURUSD", "APPROVED", dt_today + timedelta(hours=10), realized_r=1.5)
    db.add(t1)
    
    # Failed ticket (Expired)
    t2 = create_mock_ticket("PILOT-T2", "GBPUSD", "EXPIRED", dt_today + timedelta(hours=11))
    db.add(t2)
    
    # Execution log for t2
    db.add(ExecutionPrepLog(
        prep_id="PREP-T2",
        ticket_id="PILOT-T2",
        status="EXPIRED",
        created_at=dt_today + timedelta(hours=11, minutes=30),
        expires_at=dt_today + timedelta(hours=12),
        data={}
    ))
    
    db.commit()
    
    # Run aggregation
    record = fetch_session_metrics(db, today)
    
    assert record.process_metrics["total_tickets"] == 2
    assert record.performance_metrics["realized_r"] == 1.5
    assert record.process_metrics["expired_ticket_rate"] == 50.0 # 1 out of 2

def test_full_scorecard_generation(db):
    # Seed 10 days of data
    start_date = date(2026, 2, 1)
    end_date = start_date + timedelta(days=9)
    
    for i in range(10):
        curr = start_date + timedelta(days=i)
        dt_curr = datetime.combine(curr, datetime.min.time(), tzinfo=timezone.utc)
        
        # Add a passing trade each day
        db.add(create_mock_ticket(f"SC-{i}", "EURUSD", "APPROVED", dt_curr + timedelta(hours=12), realized_r=1.0))
    
    db.commit()
    
    # Build scorecard
    scorecard = build_pilot_scorecard(db, start_date, end_date)
    
    assert scorecard.aggregates["total_days"] == 10
    assert scorecard.pass_fail_summary == "PASS" # Win rate and expectancy should be good
    assert len(scorecard.sessions) == 10
    
    # Check DB logs
    log = db.query(PilotScorecardLog).filter(PilotScorecardLog.scorecard_id == scorecard.scorecard_id).first()
    assert log is not None
    assert log.pass_fail == "PASS"

def test_graduation_gate_failure(db):
    # Seed a day with high expiry rate
    day = date(2026, 2, 20)
    dt_day = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
    
    # 5 tickets, all expire
    for i in range(5):
        tid = f"FAIL-{i}"
        db.add(create_mock_ticket(tid, "EURUSD", "EXPIRED", dt_day))
        db.add(ExecutionPrepLog(prep_id=f"P-{tid}", ticket_id=tid, status="EXPIRED", created_at=dt_day, expires_at=dt_day + timedelta(hours=1), data={}))
        
    db.commit()
    
    # Run evaluation
    from services.research.pilot import fetch_session_metrics, evaluate_gate, load_pilot_config
    record = fetch_session_metrics(db, day)
    config = load_pilot_config()
    
    pf, reasons = evaluate_gate(record, config)
    assert pf == "FAIL"
    assert any("expired" in r.lower() for r in reasons)
