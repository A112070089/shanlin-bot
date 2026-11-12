"""v3.4 read-only integration does not send LINE reminders or read patient data."""
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'website'))
from integrated_app_platform_v34 import app
import pilot_backend as backend
import platform_line_bridge_v34 as line

API = '/api/pilot/platform/console/line-bot'
PAGE = '/platform/modules/appointment_reminders/line-status'

@pytest.fixture(autouse=True)
def reset_session():
    backend._sessions.clear(); backend._failed.clear()
    yield
    backend._sessions.clear(); backend._failed.clear()


def engineer():
    client=TestClient(app)
    token=backend.new_session(None, role='platform_admin', username='user')
    client.cookies.set(backend.COOKIE, token, path='/api/pilot')
    return client


def test_v34_module_center_contains_existing_line_link():
    with TestClient(app) as c:
        p=c.get('/platform/modules')
        assert p.status_code==200
        assert 'module-center-v34.js' in p.text
        js=c.get('/platform/assets/module-center-v34.js').text
        assert '既有 LINE Bot 狀態' in js
        assert 'appointment_reminders' in js
        assert 'data-clinic=' not in js
        assert c.get('/platform/modules/ai_health_summary/release').status_code==200
        assert c.get('/platform/modules/appointment_reminders/release').status_code==200


def test_v34_status_page_does_not_enable_messages():
    with TestClient(app) as c:
        p=c.get(PAGE)
        assert p.status_code==200
        assert 'line-status-v34.js' in p.text
        assert '僅檢查山林診所原有 LINE Bot' in p.text
        assert "script-src 'self'" in p.headers['content-security-policy']
        for asset in ['module-center-v34.js','line-status-v34.js','line-status-v34.css']:
            assert c.get('/platform/assets/'+asset).status_code==200
        script=c.get('/platform/assets/line-status-v34.js').text
        assert '/api/reminder/send' not in script
        assert 'POST' not in script
        assert 'lineUserId' not in script


def test_v34_line_apis_require_engineer_login():
    with TestClient(app) as c:
        assert c.get(API+'/overview').status_code in (401,403)
        assert c.get(API+'/probe').status_code in (401,403)
        assert c.post(API+'/probe').status_code==405
        assert c.post('/api/reminder/send').status_code==404


def test_overview_never_contacts_remote_or_patient_store(monkeypatch):
    def no_call(): raise AssertionError('Read-only overview must never probe')
    monkeypatch.setattr(line, '_probe_root', no_call)
    with engineer() as c:
        r=c.get(API+'/overview')
        assert r.status_code==200
        p=r.json()
        assert p['service']['state']=='not_checked'
        assert p['integration']['productionVerified'] is False
        assert p['integration']['standardFeatureActive'] is False
        assert p['integration']['scheduler']['state']=='unverified'
        assert p['integration']['security']['state']=='needs_review'
        assert p['noPatientData'] is True
        assert 'lineUserId' not in r.text and 'FIREBASE_CREDENTIALS' not in r.text


def test_probe_can_confirm_root_reachability_but_not_scheduler(monkeypatch):
    monkeypatch.setattr(line, '_probe_root', lambda:{'state':'reachable','label':'service reachable'})
    with engineer() as c:
        r=c.get(API+'/probe')
        assert r.status_code==200
        p=r.json()
        assert p['service']['state']=='reachable'
        assert p['schedulerVerified'] is False
        assert p['deliveryVerified'] is False
        assert p['productionVerified'] is False
        assert p['sendsMessages'] is False


def test_static_target_is_allowlisted_and_no_patient_endpoints():
    assert line.SHANLIN_ROOT == 'https://shanlin-bot-production.up.railway.app/'
    assert line._NoRedirect().redirect_request(None, None, 302, '', None, 'https://example.com') is None
    src=Path(line.__file__).read_text(encoding='utf-8')
    assert '/api/reminder/send' not in src
    assert 'method=\'GET\'' in src
    assert 'lineUserId' not in src


def test_v34_legacy_frontend_remains_unchanged():
    with TestClient(app) as c:
        assert c.get('/platform/assets/module-release-v33.js').status_code==200
        assert c.get('/platform/assets/module-release-v33.css').status_code==200
