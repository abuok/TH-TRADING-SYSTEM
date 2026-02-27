import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from shared.database.session import get_db
from shared.database.models import OrderTicket, ActionItem, OpsReportLog
from services.orchestration.logic.ops_engine import OpsEngine
from services.orchestration.logic.review_engine import ReviewEngine
import os

@pytest.fixture
def db_session():
    db = next(get_db())
    yield db

def test_daily_report_generation(db_session: Session):
    # Seed some data
    ticket = OrderTicket(
        pair="XAUUSD",
        status="SKIPPED",
        skip_reason="ALREADY_MOVED",
        created_at=datetime.now() - timedelta(hours=5)
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
    # Seed data to trigger action item
    for _ in range(10):
        ticket = OrderTicket(
            asset_pair="GBPJPY",
            status="SKIPPED",
            skip_reason="HIGH_SPREAD",
            created_at=datetime.now() - timedelta(days=2)
        )
        db_session.add(ticket)
    
    db_session.commit()
    
    engine = ReviewEngine(db_session)
    report, path = engine.generate_weekly_report()
    
    # Check if action item was created for HIGH_SPREAD
    ai = db_session.query(ActionItem).filter(ActionItem.title.contains("HIGH_SPREAD")).first()
    assert ai is not None
    assert ai.status == "OPEN"
    assert "weekly" in ai.source
    assert report.total_missed_r >= 