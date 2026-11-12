"""Regression: legacy clinic.js cannot show old dates or submit to :8000.

No network, no Firebase and no user data in these tests.
"""
import os
from pathlib import Path
import sys
from fastapi.testclient import TestClient
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'website'))
import integrated_app_platform_patient_stage as patient

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('PILOT_V365_SYNTHETIC_BOOKINGS_ENABLED', '1')
    monkeypatch.setattr(patient, '_relay', lambda method, *, payload=None: {
        'clinicId':'shanlin','isSynthetic':True,
        'testSchedule':{'elderlyDates':['2026-11-18','2026-11-19'],
                        'elderlyTimes':['09:00','10:00'],
                        'capacityBySlot':{'2026-11-18':{'09:00':1,'10:00':1},
                                          '2026-11-19':{'09:00':2,'10:00':1}}},
        'appointments': []})
    with TestClient(patient.app) as c:
        yield c


def test_synthetic_shanlin_form_uses_scoped_clinic_read_before_legacy_js(client):
    r=client.get('/appointment2.html?clinic=shanlin&p=A')
    assert r.status_code == 200, r.text[:500]
    html=r.text
    shim=html.index('id="shanlin-test-clinic-read-bridge"')
    legacy=html.index('<script src="clinic.js" data-api="booking"></script>')
    assert shim < legacy
    assert "url.pathname === '/api/clinic-config'" in html
    assert "url.pathname === '/api/availability'" in html
    assert "local.searchParams.set('clinic', 'shanlin')" in html
    assert "sessionStorage.removeItem('clinicConfig')" in html
    assert 'value="2026-11-02"' not in html
    assert 'value="2026-11-04"' not in html
    assert 'value="2026-11-09"' not in html
    assert 'value="08:00"' not in html
    assert html.count('--請等候測試名額載入--')==2


def test_confirm_target_is_local_8006_not_legacy_8000(client):
    html=client.get('/appointment2.html?clinic=shanlin&p=A').text
    assert '`/api/patient/shanlin/booking-test/confirm?clinic=shanlin`' in html
    assert '`${API_BASE}/api/patient/shanlin/booking-test/confirm' not in html
    assert '`${API_BASE}/api/booking/confirm`' not in html
    assert 'booking_success.html?clinic=shanlin' in html
    assert client.post('/api/booking/confirm?clinic=shanlin', json={}).status_code == 423


def test_yidian_cannot_open_shanlin_form(client):
    r=client.get('/appointment2.html?clinic=yidian&p=A',follow_redirects=False)
    assert r.status_code==303
    assert client.get('/appointment2.html',follow_redirects=False).status_code==303


def test_clinic_config_matches_test_8018_schedule(client):
    r=client.get('/api/clinic-config?clinic=shanlin')
    assert r.status_code==200
    assert r.json()['clinic']['elderlyDates']==['2026-11-18','2026-11-19']
