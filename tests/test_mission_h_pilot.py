import pytest
from datetime import date, timedelta, datetime, timezone
from sqlalchemy.orm import Session
from shared.database.models import (
    OrderTicket, ExecutionPrepLog, PilotSessionLog, PilotScorecardLog, TuningProposalLog
)
from services.research.pilot import build_pilot_scorecard, fetch_session_metrics
from shared.logic.sessions import get_nairobi_time

def test_pilot_metrics_aggregation(db):
    # Seed data for a passing session
    today = date(2026, 2, 28)
    dt_today = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
    
    # Passing ticket
    t1 = OrderTicket(
        ticket_id="PILOT-T1", 
        pair="EURUSD", 
        status="APPROVED", 
        realized_r=1.5, 
        created_at=dt_today + timedelta(hours=10)
    )
    db.add(t1)
    
    # Failed ticket (Expired)
    t2 = OrderTicket(
        ticket_id="PILOT-T2", 
        pair="GBPUSD", 
        status="EXPIRED", 
        created_at=dt_today + timedelta(hours=11)
    )
    db.add(t2)
    
    # Execution log for t2
    db.add(ExecutionPrepLog(
        ticket_id="PILOT-T2",
        status="EXPIRED",
        created_at=dt_today + timedelta(hours=11, minutes=30),
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
        db.add(OrderTicket(
            ticket_id=f"SC-{i}",
            pair="EURUSD",
            status="APPROVED",
            realized_r=1.0,
            created_at=dt_curr + timedelta(hours=12)
        ))
    
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
        db.add(OrderTicket(ticket_id=f"FAIL-{i}", pair="EURUSD", status="EXPIRED", created_at=dt_day))
        db.add(ExecutionPrepLog(ticket_id=f"FAIL-{i}", status="EXPIRED", created_at=dt_day, data={}))
        
    db.commit()
    
    # Run evaluation
    from services.research.pilot import fetch_session_metrics, evaluate_gate, load_pilot_config
    record = fetch_session_metrics(db, day)
    config = load_pilot_config()
    
    pf, reasons = evaluate_gate(record, config)
    assert pf == "FAIL"
    assert any("expired" in r.lower() for r in reasons)
