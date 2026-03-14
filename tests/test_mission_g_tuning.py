import pytest
from datetime import timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.database.models import (
    Base,
    OrderTicket,
    AlignmentLog,
    ExecutionPrepLog,
    TuningProposalLog,
)
from services.research.tuning import (
    fetch_tuning_metrics,
    generate_proposals,
    generate_tuning_report,
)
from shared.logic.sessions import get_nairobi_time

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


def test_tuning_metrics_gathering(db):
    now_eat = get_nairobi_time()
    past = now_eat - timedelta(days=2)

    # Seed 3 tickets
    t1 = OrderTicket(
        ticket_id="T1",
        setup_packet_id=1,
        risk_packet_id=1,
        pair="EURUSD",
        direction="BUY",
        entry_price=1.0,
        stop_loss=0.9,
        take_profit_1=1.2,
        lot_size=1.0,
        risk_usd=100.0,
        risk_pct=1.0,
        rr_tp1=2.0,
        idempotency_key="K1",
        created_at=past,
    )
    t2 = OrderTicket(
        ticket_id="T2",
        setup_packet_id=2,
        risk_packet_id=2,
        pair="GBPUSD",
        direction="SELL",
        entry_price=1.0,
        stop_loss=0.9,
        take_profit_1=1.2,
        lot_size=1.0,
        risk_usd=100.0,
        risk_pct=1.0,
        rr_tp1=2.0,
        idempotency_key="K2",
        created_at=past,
    )
    db.add_all([t1, t2])

    # Create 2 aligned, 1 unaligned
    # Pair fundamentals GBPCAD, GBPJPY
    cutoff = now_eat - timedelta(hours=1)
    g1 = AlignmentLog(
        pair="GBPCAD",
        alignment_score=95,
        is_aligned=True,
        result_json={},
        created_at=cutoff + timedelta(minutes=10),
    )
    g2 = AlignmentLog(
        pair="GBPJPY",
        alignment_score=60,
        is_aligned=False,
        result_json={},
        created_at=cutoff + timedelta(minutes=20),
    )
    db.add_all([g1, g2])

    db.commit()

    start_date = now_eat - timedelta(days=7)
    metrics = fetch_tuning_metrics(db, start_date, now_eat)

    assert metrics["total_tickets"] == 2
    # AlignmentLog created_at is strictly > start_date (past)
    assert metrics["guardrails_blocks"] == 1
    # avg of 95 and 60 is 77.5
    assert metrics["avg_discipline_score"] == 77.5


def test_heuristic_proposals():
    # Test Guardrails proposal (Block rate > 40%)
    metrics = {
        "start_date": "2026-02-01",
        "end_date": "2026-02-07",
        "total_tickets": 10,
        "guardrails_blocks": 5,  # 50%
        "avg_discipline_score": 40.0,
        "total_prep_logs": 10,
        "expired_prep_logs": 1,  # 10% (No proposal)
        "total_suggestions": 10,
        "move_sl_suggestions": 5,  # < 20
        "risk_off_policies": 1,
        "critical_alerts": 10,
    }

    props = generate_proposals(metrics)
    assert len(props) == 1
    assert props[0].target == "guardrails"
    assert "Relax Discipline Score" in props[0].title


def test_full_report_generation_integration(db):
    now_eat = get_nairobi_time()
    past = now_eat - timedelta(days=1)

    # Force some metrics to trigger multiple proposals

    # 1. High Guardrails block rate
    t1 = OrderTicket(
        ticket_id="T1",
        setup_packet_id=1,
        risk_packet_id=1,
        pair="EURUSD",
        direction="BUY",
        entry_price=1.0,
        stop_loss=0.9,
        take_profit_1=1.2,
        lot_size=1.0,
        risk_usd=100.0,
        risk_pct=1.0,
        rr_tp1=2.0,
        idempotency_key="K1",
        created_at=past,
    )
    db.add(t1)

    db.add(
        AlignmentLog(
            pair="EURUSD",
            alignment_score=10,
            is_aligned=False,
            result_json={},
            created_at=past,
        )
    )
    db.add(
        AlignmentLog(
            pair="GBPUSD",
            alignment_score=20,
            is_aligned=False,
            result_json={},
            created_at=past,
        )
    )

    # 2. High Execution Expire rate
    db.add(
        ExecutionPrepLog(
            ticket_id="T1",
            expires_at=now_eat,
            data={},
            status="EXPIRED",
            created_at=past,
        )
    )

    db.commit()

    # Run Tuning Report
    report = generate_tuning_report(db, days_back=7)

    # Check return structure
    assert report.report_id.startswith("TUNE-")
    assert len(report.proposals) >= 2  # Should have guardrails and prep queue proposals

    targets = [p.target for p in report.proposals]
    assert "guardrails" in targets
    assert "queue" in targets

    # Check DB Logging
    log = (
        db.query(TuningProposalLog)
        .filter(TuningProposalLog.report_id == report.report_id)
        .first()
    )
    assert log is not None
    assert log.status == "OPEN"

    # Validate payload mock API execution logic
    data = log.data
    prop_id = data["proposals"][0]["id"]

    # Mocking what the dashboard endpoint does
    for p in data["proposals"]:
        if p["id"] == prop_id:
            p["status"] = "ACCEPT"
            p["reviewer_notes"] = "Looks good"

    from sqlalchemy.orm.attributes import flag_modified

    log.data = data
    flag_modified(log, "data")
    db.commit()

    updated = (
        db.query(TuningProposalLog)
        .filter(TuningProposalLog.report_id == report.report_id)
        .first()
    )
    assert updated.data["proposals"][0]["status"] == "ACCEPT"
    assert updated.data["proposals"][0]["reviewer_notes"] == "Looks good"
