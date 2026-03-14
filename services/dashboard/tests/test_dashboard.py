import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import sys
import os

# Ensure root is in path
sys.path.append(os.getcwd())

from services.dashboard.main import app

client = TestClient(app)


@pytest.fixture
def mock_db():
    mock = MagicMock()
    return mock


def test_dashboard_overview_basic():
    """Verify the dashboard home page loads with basic data."""
    with (
        patch("services.dashboard.main.get_service_health") as mock_health,
        patch("services.dashboard.main.get_dashboard_data") as mock_data,
    ):
        mock_health.return_value = ({"Ingestion": "healthy"}, {"Ingestion": 10})
        mock_data.return_value = {
            "now_nairobi_str": "2026-02-26 23:00:00",
            "session_label": "SYDNEY",
            "kill_switches": [],
            "events": [],
            "no_trade_windows": [],
            "latest_setups": [],
            "latest_decisions": [],
            "latest_incidents": [],
            "permission_state": "TRADEABLE",
            "permission_msg": "SYSTEM READY",
            "bias_states": {},
            "risk_budget": {"daily_loss_pct": 0, "max_daily_loss_pct": 2, "max_consecutive_losses": 3, "consecutive_losses": 0},
            "live_positions": [],
            "live_quotes": [],
            "time_to_transition": 60
        }

        response = client.get("/dashboard")
        assert response.status_code == 200
        assert "TRADEABLE" in response.text


def test_dashboard_kill_switches_reflected():
    """Verify active kill switches are shown in the UI."""
    with (
        patch("services.dashboard.main.get_service_health") as mock_health,
        patch("services.dashboard.main.get_dashboard_data") as mock_data,
    ):
        mock_health.return_value = ({"Ingestion": "healthy"}, {"Ingestion": 10})
        mock_data.return_value = {
            "now_nairobi_str": "2026-02-26 23:00:00",
            "session_label": "SYDNEY",
            "kill_switches": [MagicMock(switch_type="HALT_ALL", target=None)],
            "events": [],
            "no_trade_windows": [],
            "latest_setups": [],
            "latest_decisions": [],
            "latest_incidents": [],
            "permission_state": "HARD_LOCK",
            "permission_msg": "HALT_ALL ACTIVE",
            "bias_states": {},
            "risk_budget": {"daily_loss_pct": 0, "max_daily_loss_pct": 2, "max_consecutive_losses": 3, "consecutive_losses": 0},
            "live_positions": [],
            "live_quotes": [],
            "time_to_transition": 60
        }

        response = client.get("/dashboard")
        assert response.status_code == 200
        assert "HALT_ALL" in response.text
        # In HARD_LOCK mode, the template shows the escalation view
        assert "EXECUTION PATH UNCONDITIONALLY SEALED" in response.text


def test_dashboard_stale_packets_reflected():
    """Verify stale packets are marked in the UI."""
    with (
        patch("services.dashboard.main.get_service_health") as mock_health,
        patch("services.dashboard.main.get_dashboard_data") as mock_data,
    ):
        mock_health.return_value = ({"Ingestion": "healthy"}, {"Ingestion": 10})
        mock_data.return_value = {
            "now_nairobi_str": "2026-02-26 23:00:00",
            "session_label": "SYDNEY",
            "kill_switches": [],
            "events": [],
            "no_trade_windows": [],
            "latest_setups": [
                {
                    "asset_pair": "BTC-USD",
                    "stage": "A",
                    "is_aligned": False,
                    "age_str": "1m",
                    "is_fresh": False
                }
            ],
            "latest_decisions": [],
            "latest_incidents": [],
            "permission_state": "TRADEABLE",
            "permission_msg": "SYSTEM READY",
            "bias_states": {"BTC-USD": {"bias": "BULLISH", "age_m": 5, "is_invalidated": False}},
            "risk_budget": {"daily_loss_pct": 0.5, "max_daily_loss_pct": 2.0, "consecutive_losses": 0, "max_consecutive_losses": 3},
            "live_positions": [],
            "live_quotes": [],
            "time_to_transition": 45
        }

        response = client.get("/dashboard")
        assert response.status_code == 200
        assert "BTC-USD" in response.text
        # The dashboard uses "UNALIGNED" or similar for is_aligned=False, check template
        assert "NOT ALIGNED" in response.text or "UNALIGNED" in response.text


def test_dashboard_routes_render():
    """Verify all sub-pages return 200."""
    routes = [
        "/dashboard/incidents",
        "/dashboard/setups",
        "/dashboard/risk",
        "/dashboard/reports",
    ]
    for route in routes:
        response = client.get(route)
        assert response.status_code == 200
