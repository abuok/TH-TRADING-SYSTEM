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
        }

        response = client.get("/dashboard")
        assert response.status_code == 200
        assert "HALT_ALL" in response.text
        assert "GLOBAL" in response.text


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
                    "score": 80.0,
                    "is_fresh": False,
                }
            ],
            "latest_decisions": [],
            "latest_incidents": [],
        }

        response = client.get("/dashboard")
        assert response.status_code == 200
        assert "BTC-USD" in response.text
        assert "STALE" in response.text


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
