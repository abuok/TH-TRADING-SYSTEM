from fastapi.testclient import TestClient

from services.dashboard.main import app
from shared.ui.theme import ACCENTS, NEUTRALS

client = TestClient(app)


def test_theme_preview_route():
    response = client.get("/dashboard/theme")
    assert response.status_code == 200
    assert "Dashboard Theme Palette" in response.text
    for _name, hexcode in ACCENTS.items():
        assert hexcode in response.text
    for _name, hexcode in NEUTRALS.items():
        assert hexcode in response.text
