from fastapi.testclient import TestClient
import sys
import os


# Add service directory to path for testing
def test_health_check(service_name):
    sys.path.append(os.path.abspath(f"services/{service_name}"))
    from main import app

    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == service_name
    sys.path.pop()


def test_ingestion_health():
    test_health_check("ingestion")


def test_technical_health():
    test_health_check("technical")


def test_risk_health():
    test_health_check("risk")


def test_journal_health():
    test_health_check("journal")
