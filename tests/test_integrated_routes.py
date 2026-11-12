"""Pure read-only local route smoke test for the integrated preview.
Run from the original project root:
    python -m pytest -q tests/test_integrated_routes.py
"""
import sys
from pathlib import Path

from fastapi.testclient import TestClient

SITE = Path(__file__).resolve().parents[1] / "website"
sys.path.insert(0, str(SITE))
from integrated_app import app  # noqa: E402

client = TestClient(app)


def test_home_and_booking_page():
    response = client.get("/")
    assert response.status_code == 200
    assert "const api=String(window.SITE?.bookingApi || location.origin)" in response.text
    assert client.get("/appointment2.html").status_code == 200


def test_same_origin_site_configuration():
    response = client.get("/site-config.js")
    assert response.status_code == 200
    assert "bookingApi:root" in response.text
    assert "isIntegrated:true" in response.text
    assert "private_key" not in response.text


def test_pilot_frontend_and_api_routes():
    assert client.get("/pilot?clinic=shanlin&view=admin").status_code == 200
    assert client.get("/pilot/assets/pilot.js").status_code == 200
    assert client.get("/pilot/assets/pilot.css").status_code == 200
    response = client.get("/api/pilot/admin/session")
    assert response.status_code == 401


def test_legacy_admin_navigation():
    response = client.get("/admin.html")
    assert response.status_code == 200
    assert "/pilot?clinic=shanlin" in response.text


def test_protect_local_sources_and_untrusted_files():
    for path in ("/main.py", "/pilot_backend.py", "/.env", "/requirements.txt", "/assets/.env", "/css/../../.env"):
        assert client.get(path).status_code in (400, 404), path
    assert client.get("/api/firebase/test-write").status_code == 404


def test_original_api_health_works_without_writing():
    response = client.get("/api/booking/health")
    assert response.status_code == 200
    assert response.json().get("status") == "success"


def test_taigi_routers_present_but_disabled_by_default(monkeypatch):
    monkeypatch.delenv("TAIGI_TTS_ENABLED", raising=False)
    monkeypatch.delenv("TAIGI_STT_ENABLED", raising=False)
    response = client.get("/api/taigi_tts/health")
    assert response.status_code == 200
    assert response.json()["enabled"] is False
    response = client.get("/api/taigi_stt/health")
    assert response.status_code == 200
    assert response.json()["enabled"] is False
