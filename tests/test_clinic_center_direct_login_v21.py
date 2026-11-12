"""UI regression tests for no-intermediate-page clinic center login."""
from pathlib import Path
import sys

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'website'))
from integrated_app_platform_v2 import app
from pilot_backend import COOKIE, new_session


def test_signed_out_clinic_center_is_hidden_until_checked():
    with TestClient(app) as client:
        response = client.get('/platform/clinics')
        assert response.status_code == 200
        assert '<main id="clinicCenterMain" hidden>' in response.text
        assert '新增診所草稿' in response.text
        assert client.get('/api/pilot/platform/console/session').status_code in (401, 403)


def test_login_redirect_and_return_have_fixed_allowlisted_target():
    with TestClient(app) as client:
        center_script = client.get('/platform/assets/clinic-center.js').text
        engineer_script = client.get('/platform/assets/platform.js').text
        assert "location.replace('/platform/admin?next=%2Fplatform%2Fclinics')" in center_script
        assert "e.status===401||e.status===403" in center_script
        assert '前往工程師登入' not in center_script
        assert "get('next') === '/platform/clinics'" in engineer_script
        assert engineer_script.count('location.replace(CLINIC_CENTER_AFTER_LOGIN)') == 2
        assert 'location.replace(new URLSearchParams' not in engineer_script


def test_existing_engineer_session_can_use_center():
    token = new_session(None, role='platform_admin', username='v21_test')
    with TestClient(app) as client:
        client.cookies.set(COOKIE, token, path='/api/pilot')
        assert client.get('/api/pilot/platform/console/session').status_code == 200
        assert client.get('/api/pilot/platform/console/clinic-registry').status_code == 200
        assert client.get('/platform/clinics').status_code == 200


def test_clinic_account_cannot_use_engineer_registry():
    token = new_session('shanlin', role='clinic_admin', username='shanlin_admin')
    with TestClient(app) as client:
        client.cookies.set(COOKIE, token, path='/api/pilot')
        assert client.get('/api/pilot/platform/console/clinic-registry').status_code == 403
        assert client.get('/api/pilot/platform/console/session').status_code == 403
