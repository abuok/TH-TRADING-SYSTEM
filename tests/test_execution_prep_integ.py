import pytest
from fastapi.testclient import TestClient
from services.dashboard.main import app
from shared.database.session import get_db
from shared.database.models import OrderTicket, ExecutionPrepLog
from shared.logic.sessions import get_nairobi_time
from datetime import timedelta

client = TestClient(app)

@pytest.fixture
def db():
    db = next(get_db())
    yield db

def test_execution_prep_lifecycle_integration(db):
    # 1. Create a ticket in IN_REVIEW
    ticket_id = "INTEG_TICKET_1"
    # Cleanup if exists
    db.query(OrderTicket).filter(OrderTicket.ticket_id == ticket_id).delete()
    db.query(ExecutionPrepLog).filter(ExecutionPrepLog.ticket_id == ticket_id).delete()
    db.commit()

    ticket = OrderTicket(
        ticket_id=ticket_id,
        pair="XAUUSD",
        direction="BUY",
        entry_price=2000.0,
        stop_loss=1990.0,
        take_profit_1=2020.0,
        risk_usd=100.0,
        risk_pct=1.0,
        lot_size=0.1,
        rr_tp1=2.0,
        status="IN_REVIEW",
        expires_at=get_nairobi_time() + timedelta(minutes=10),
        setup_packet_id=1,
        risk_packet_id=1,
        idempotency_key="INTEG_IK_1"
    )
    db.add(ticket)
    db.commit()

    # 2. Approve the ticket via API
    response = client.post(f"/api/tickets/{ticket_id}/approve")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "prep_id" in data

    # 3. Fetch the Execution Prep
    response = client.get(f"/api/execution-prep/{ticket_id}")
    assert response.status_code == 200
    prep = response.json()
    assert prep["ticket_id"] == ticket_id
    assert prep["status"] == "ACTIVE"
    assert len(prep["preflight_checks"]) > 0

    # 4. Perform an Override
    override_reason = "Test override reason"
    response = client.post(f"/api/execution-prep/{ticket_id}/override?reason={override_reason}")
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    # 5. Verify the DB state
    log = db.query(ExecutionPrepLog).filter(ExecutionPrepLog.ticket_id == ticket_id).first()
    assert log.status == "OVERRIDDEN"
    assert log.override_reason == override_reason
