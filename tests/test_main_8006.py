"""Local 8006 integration checks; no real credentials, network or patient data."""
import sys
from pathlib import Path
from hashlib import sha256

import pytest
from fastapi.testclient import TestClient

SITE = Path(__file__).resolve().parents[1] / 'website'
sys.path.insert(0, str(SITE))
from integrated_app_platform_main import app  # noqa:E402
import pilot_backend as auth  # noqa:E402


@pytest.fixture
def local_session(monkeypatch):
    monkeypatch.setattr(auth, '_sessions', {})
    monkeypatch.setenv('PILOT_V365_SYNTHETIC_BOOKINGS_ENABLED', '1')
    with TestClient(app) as client:
        yield client


def sign_in(client, clinic, role='clinic_admin', legacy=False):
    token = auth.new_session(clinic, role=role, username='synthetic-test')
    session = auth._sessions[sha256(token.encode()).hexdigest()]
    if legacy:
        session['legacyConfig'] = {'name': '山林診所'}
    client.cookies.set(auth.COOKIE, token, path='/api/pilot')
    return session


def test_existing_home_and_engineer_console_preserved(local_session):
    client = local_session
    for path in ('/', '/platform/admin', '/platform/operations', '/api/pilot/clinics/shanlin/public'):
        res = client.get(path)
        assert res.status_code == 200, (path, res.status_code)
    assert client.get('/platform/admin').status_code == 200


def test_same_page_clinic_staff_ui_no_external_admin_buttons(local_session):
    client = local_session
    html = client.get('/pilot?clinic=shanlin&view=admin')
    assert html.status_code == 200
    assert 'id="shanlinUnifiedBookings"' in html.text
    assert 'id="shanlinBookingFrame"' in html.text
    assert 'https://shanlin-bot-production.up.railway.app/admin.html' not in html.text
    script = client.get('/pilot/assets/pilot.js')
    assert script.status_code == 200
    assert "frame.setAttribute('src','/api/pilot/admin/shanlin/booking-frame')" in script.text
    assert client.get('/pilot/assets/pilot.css').status_code == 200


def test_booking_frame_refuses_no_login_and_wrong_clinic(local_session):
    client = local_session
    path = '/api/pilot/admin/shanlin/booking-frame'
    assert client.get(path).status_code == 401
    sign_in(client, 'yidian')
    assert client.get(path).status_code == 403
    sign_in(client, None, role='platform_admin')
    assert client.get(path).status_code == 403
    sign_in(client, 'shanlin', legacy=True)
    res = client.get(path)
    assert res.status_code == 200
    assert 'unified-embedded' in res.text
    assert 'frame-ancestors \'self\'' in res.headers['Content-Security-Policy']


def test_staff_bookings_api_auth_and_tenant_guard(local_session):
    client = local_session
    path = '/api/pilot/admin/shanlin/booking-stage/appointments'
    assert client.get(path).status_code == 401
    assert client.post(path, json={'name': 'fake'}).status_code == 401
    sign_in(client, 'yidian')
    assert client.get(path).status_code == 403
    assert client.post(path, json={'name': 'fake'}).status_code == 403


def test_disable_flag_blocks_booking_access(local_session, monkeypatch):
    client = local_session
    sign_in(client, 'shanlin', legacy=True)
    monkeypatch.setenv('PILOT_V365_SYNTHETIC_BOOKINGS_ENABLED', '0')
    assert client.get('/api/pilot/admin/shanlin/booking-frame').status_code == 423
    assert client.get('/api/pilot/admin/shanlin/booking-stage/appointments').status_code == 423


def test_original_patient_booking_write_is_disabled(local_session):
    client = local_session
    res = client.post('/api/booking/confirm?clinic=shanlin', json={})
    assert res.status_code == 423


def test_no_remote_host_can_open_staff_preview(local_session):
    with TestClient(app, base_url='http://not-local.example') as remote:
        res = remote.get('/pilot?clinic=shanlin&view=admin')
        assert res.status_code == 403
