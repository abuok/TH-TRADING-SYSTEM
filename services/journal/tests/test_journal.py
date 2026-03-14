from fastapi.testclient import TestClient

from services.journal.main import app

# The conftest.py already handles engine/SessionLocal/Base.metadata.create_all

client = TestClient(app)


def test_log_setup_scoring():
    setup_data = {
        "schema_version": "1.0.0",
        "asset_pair": "EURUSD",
        "strategy_name": "PHX",
        "entry_price": 1.0850,
        "stop_loss": 1.0800,
        "take_profit": 1.1000,
        "timeframe": "1H",
        "session_levels": {"asia_high": 1.0860},
    }
    # Test A+ score
    response = client.post("/log/setup?score=95.0", json=setup_data)
    assert response.status_code == 200
    assert response.json()["label"] == "A+"

    # Test C score
    response = client.post("/log/setup?score=65.0", json=setup_data)
    assert response.status_code == 200
    assert response.json()["label"] == "C"


def test_status_taken_on_outcome():
    setup_data = {
        "schema_version": "1.0.0",
        "asset_pair": "EURUSD",
        "strategy_name": "PHX",
        "entry_price": 1.0,
        "stop_loss": 0.9,
        "take_profit": 1.2,
        "timeframe": "1H",
    }
    # Create setup
    res = client.post("/log/setup?score=80.0", json=setup_data)
    setup_id = res.json()["id"]

    # Log outcome
    client.post(
        f"/log/outcome?setup_id={setup_id}&is_win=True&r_multiple=2.0&pnl=100.0"
    )

    # Check report for TAKEN status
    res = client.get("/report/daily")
    assert "status-taken" in res.text


def test_daily_report_enhanced():
    response = client.get("/report/daily")
    assert response.status_code == 200
    assert "Daily Performance Report" in response.text
    assert "Potential Profit Missed" in response.text
    assert "Actual PnL" in response.text


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
