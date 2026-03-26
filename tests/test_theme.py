from fastapi.testclient import TestClient

from services.dashboard.main import app

client = TestClient(app)


def test_theme_preview_route_removed():
    """
    The /dashboard/theme route was removed during the 4-hub consolidation.
    This test guards against its accidental re-introduction.
    The theme system (ACCENTS / NEUTRALS) is still importable as a module.
    """
    response = client.get("/dashboard/theme")
    assert response.status_code == 404


def test_theme_module_importable():
    """The theme color palette module must remain importable."""
    from shared.ui.theme import ACCENTS, NEUTRALS

    assert len(ACCENTS) > 0
    assert len(NEUTRALS) > 0
    # Verify values are hex strings
    for name, hexcode in {**ACCENTS, **NEUTRALS}.items():
        assert hexcode.startswith("#"), f"{name} value {hexcode!r} is not a hex color"
