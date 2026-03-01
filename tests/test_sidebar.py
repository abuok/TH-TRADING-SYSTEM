import pytest
from fastapi.testclient import TestClient
from services.dashboard.main import app

client = TestClient(app)

def test_sidebar_renders_on_dashboard():
    response = client.get("/dashboard")
    assert response.status_code == 200
    content = response.text
    # Verify sidebar sections
    assert "Operations" in content
    assert "Trading" in content
    assert "Analytics" in content
    assert "System" in content
    
    # Verify specific links
    assert "Queue" in content
    assert "Pilot" in content
    assert "Execution Prep" in content
    
    # Verify sidebar structure
    assert 'class="sidebar"' in content
    assert 'class="sidebar-nav"' in content
