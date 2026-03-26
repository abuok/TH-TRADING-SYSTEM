from fastapi.testclient import TestClient

from services.dashboard.main import app

client = TestClient(app)


def test_sidebar_renders_on_dashboard():
    response = client.get("/dashboard")
    assert response.status_code == 200
    content = response.text

    # Verify sidebar section heading (consolidated architecture)
    assert "Tactical Hubs" in content

    # Verify the 4 consolidated hub links are present
    assert "Command Center" in content
    assert "Order Flow" in content
    assert "Strategy Context" in content
    assert "Node Telemetry" in content

    # Verify sidebar structural classes
    assert 'class="sidebar"' in content
    assert 'class="sidebar-nav"' in content
