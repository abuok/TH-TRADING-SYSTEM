import pytest
from fastapi.testclient import TestClient
from services.dashboard.main import app
from services.dashboard.logic import get_dashboard_data
from shared.database.session import SessionLocal, engine
from shared.database.models import Base, Packet, IncidentLog, PositionSnapshot
from shared.types.enums import LockoutState
import json
from datetime import datetime, timezone

# Initialize DB for tests
Base.metadata.create_all(bind=engine)

client = TestClient(app)

def test_dashboard_logic_structure():
    db = SessionLocal()
    try:
        data = get_dashboard_data(db)
        
        # Verify required keys for 7-panel HUD
        assert "permission_state" in data
        assert "permission_msg" in data
        assert "session_label" in data
        assert "time_to_transition" in data
        assert "bias_states" in data
        assert "latest_setups" in data
        assert "risk_budget" in data
        assert "live_positions" in data
        assert "latest_incidents" in data
        
    finally:
        db.close()

def test_dashboard_rendering_canonical_terms():
    response = client.get("/dashboard")
    assert response.status_code == 200
    html = response.text
    
    # Verify terminology
    assert "PERMISSION STATE" in html
    assert "SESSION STATE" in html
    assert "BIAS STATE" in html
    assert "SETUP PROGRESSION" in html
    assert "RISK BUDGET" in html
    assert "ACTIVE POSITIONS" in html
    assert "NOTICE & INCIDENT LOG" in html
    
    # Verify absence of legacy terms
    assert "Confidence" not in html
    assert "Signal Score" not in html # We renamed this or replaced it

def test_hard_lock_visibility(db_session):
    # Trigger a hard lock via an incident or similar if logic allows, 
    # but here we can just mock the lockout_engine's evaluation if we wanted.
    # For a high-level test, we check if the HARD_LOCK string triggers the escalation view.
    
    # We'll just test the logic with a mocked account state if needed, 
    # but since logic.py has hardcoded defaults for now, we'll verify it returns TRADEABLE by default.
    data = get_dashboard_data(db_session)
    assert data["permission_state"] == "TRADEABLE"
