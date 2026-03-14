import os
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from services.orchestration.logic.ops_engine import OpsEngine
from services.orchestration.logic.review_engine import ReviewEngine
from shared.database.models import ActionItem, OrderTicket, Packet, Run
from shared.database.session import get_db


@pytest.fixture
def db_session():
    db = next(get_db())
    yield db


def create_dummy_packet(db: Session, p_type: str):
    # Create a Run first
    run = Run(run_id=f"RUN_{uuid.uuid4().hex[:8]}", status="completed")
    db.add(run)
    db.commit()
    db.refresh(run)

    p = Packet(run_id=run.id, packet_type=p_type, schema_version="1.0", data={})
    db.add(p)
    db.commit()
    db.refresh(p)
    return p.id


def test_daily_report_generation(db_session: Session):
    # Seed packets
    p_id = create_dummy_packet(db_session, f"P_{uuid.uuid4().hex[:8]}")

    # Seed some data
    ticket = OrderTicket(
        ticket_id=f"T_{uuid.uuid4().hex[:8]}",
        setup_packet_id=p_id,
        risk_packet_id=p_id,
        pair="XAUUSD",
        direction="BUY",
        entry_price=2000.0,
        stop_loss=1990.0,
        take_profit_1=2020.0,
        lot_size=0.1,
        risk_usd=100.0,
        risk_pct=1.0,
        rr_tp1=2.0,
        idempotency_key=str(uuid.uuid4()),
        status="SKIPPED",
        skip_reason="ALREADY_MOVED",
        created_at=datetime.now() - timedelta(hours=5),
    )
    db_session.add(ticket)
    db_session.commit()

    engine = OpsEngine(db_session)
    report, path = engine.generate_daily_report()

    assert report.report_id.startswith("ops_")
    assert report.queue_skips >= 1
    assert "ALREADY_MOVED" in report.top_skip_reasons
    assert os.path.exists(path)


def test_weekly_review_action_items(db_session: Session):
    p_id = create_dummy_packet(db_session, f"P_{uuid.uuid4().hex[:8]}")

    # Seed data to trigger action item
    for i in range(10):
        ticket = OrderTicket(
            ticket_id=f"TW_{uuid.uuid4().hex[:8]}_{i}",
            setup_packet_id=p_id,
            risk_packet_id=p_id,
            pair="GBPJPY",
            direction="SELL",
            entry_price=180.0,
            stop_loss=181.0,
            take_profit_1=178.0,
            lot_size=0.1,
            risk_usd=100.0,
            risk_pct=1.0,
            rr_tp1=2.0,
            idempotency_key=f"IK_{uuid.uuid4().hex[:8]}_{i}",
            status="SKIPPED",
            skip_reason="HIGH_SPREAD",
            created_at=datetime.now() - timedelta(days=2),
        )
        db_session.add(ticket)

    db_session.commit()

    engine = ReviewEngine(db_session)
    report, path = engine.generate_weekly_report()

    # Check if action item was created for HIGH_SPREAD
    ai = (
        db_session.query(ActionItem)
        .filter(ActionItem.title.contains("HIGH_SPREAD"), ActionItem.status == "OPEN")
        .first()
    )
    assert ai is not None
    assert "weekly" in ai.source
