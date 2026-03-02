from fastapi.testclient import TestClient
from services.dashboard.main import app
import os

client = TestClient(app)

def test_dashboard_auth_gating():
    """Verify that dashboard is protected when auth is enabled."""
    os.environ["DASHBOARD_AUTH_ENABLED"] = "true"
    os.environ["DASHBOARD_USERNAME"] = "testuser"
    os.environ["DASHBOARD_PASSWORD"] = "testpass"
    
    # Unauthorized request
    response = client.get("/dashboard")
    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers
    
    # Authorized request
    response = client.get("/dashboard", auth=("testuser", "testpass"))
    assert response.status_code == 200

def test_dashboard_no_auth_when_disabled():
    """Verify that dashboard is accessible without auth when disabled."""
    os.environ["DASHBOARD_AUTH_ENABLED"] = "false"
    
    response = client.get("/dashboard")
    assert response.status_code == 200
