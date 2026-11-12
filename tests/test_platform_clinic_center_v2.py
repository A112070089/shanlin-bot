"""v2 draft onboarding tests: isolated temporary files, never real patient/clinic data."""
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'website'))

from integrated_app_platform_v2 import app
import platform_clinic_registry as registry
from pilot_backend import COOKIE, new_session


@pytest.fixture
def isolated_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, '_paths', lambda: (
        tmp_path / 'registry.json', tmp_path / 'registry.lock'))
    return tmp_path


def engineer_client():
    client = TestClient(app)
    token = new_session(None, role='platform_admin', username='engineer_test')
    client.cookies.set(COOKIE, token, path='/api/pilot')
    return client


def create_payload(rev, slug='test-clinic'):
    return {'clinicId': slug, 'displayName': '示範第三診所',
            'notes': '待建立資料庫', 'expectedRevision': rev}


def test_v2_pages_route_first_and_do_not_change_v1(isolated_registry):
    with TestClient(app) as c:
        dashboard = c.get('/platform/admin')
        assert dashboard.status_code == 200
        assert '/platform/clinics' in dashboard.text
        assert '平台總覽' in dashboard.text
        assert c.get('/platform/clinics').status_code == 200
        assert '新增診所草稿' in c.get('/platform/clinics').text
        assert c.get('/platform/assets/clinic-center.js').status_code == 200
        assert c.get('/platform/assets/clinic-center.css').status_code == 200
        assert c.get('/api/pilot/platform/console/clinic-registry').status_code in (401, 403)
        assert c.get('/api/pilot/platform/console/state').status_code in (401, 403)


def test_two_clients_share_registry_but_local_not_firebase(isolated_registry):
    with engineer_client() as a, engineer_client() as b:
        initial = a.get('/api/pilot/platform/console/clinic-registry').json()
        assert {c['clinicId'] for c in initial['existingClinics']} == {'shanlin', 'yidian'}
        r = a.post('/api/pilot/platform/console/clinic-registry/drafts',
                   json=create_payload(initial['revision']),
                   headers={'Origin': 'http://testserver',
                            'X-Pilot-CSRF': a.get('/api/pilot/platform/console/session').json()['csrf']})
        assert r.status_code == 200, r.text
        assert len(b.get('/api/pilot/platform/console/clinic-registry').json()['drafts']) == 1
        assert not (isolated_registry / 'shanlin').exists()
        assert not (isolated_registry / 'yidian').exists()
        assert list(isolated_registry.glob('*')) == [isolated_registry / 'registry.lock', isolated_registry / 'registry.json'] or set(isolated_registry.glob('*')) == {isolated_registry / 'registry.lock', isolated_registry / 'registry.json'}
        data = (isolated_registry / 'registry.json').read_text(encoding='utf-8')
        assert 'password' not in data.lower()
        assert 'firebase' not in data.lower()
        assert (isolated_registry / 'registry.json').stat().st_mode & 0o777 == 0o600


def test_create_edit_archive_and_revision_conflict(isolated_registry):
    start = registry.read_state()['revision']
    state = registry.create_draft(clinic_id='test-clinic', display_name='新診所',
                                  notes='', expected_revision=start, actor='engineer')
    assert state['drafts'][0]['readyForBooking'] is False
    assert state['drafts'][0]['accountCreated'] is False
    assert state['drafts'][0]['storageConnected'] is False
    with pytest.raises(registry.RevisionConflict):
        registry.create_draft(clinic_id='second-clinic', display_name='另一診所',
                              notes='', expected_revision=start, actor='engineer')
    changed = registry.update_draft(clinic_id='test-clinic', display_name='改名診所',
                                     notes='內部草稿', archived=True,
                                     expected_revision=state['revision'], actor='engineer')
    assert changed['drafts'][0]['archived'] is True
    assert changed['drafts'][0]['displayName'] == '改名診所'
    assert registry.audit_tail()[0]['action'] == 'draft_archived'
    restored = registry.update_draft(clinic_id='test-clinic', display_name='改名診所',
                                     notes='內部草稿', archived=False,
                                     expected_revision=changed['revision'], actor='engineer')
    assert restored['drafts'][0]['archived'] is False


def test_real_clinics_and_reserved_slugs_never_modified(isolated_registry):
    for slug in ('shanlin', 'yidian', 'admin', 'platform', 'api', 'UPPER', 'ab'):
        with pytest.raises(ValueError):
            registry.create_draft(clinic_id=slug, display_name='測試診所', notes='',
                                  expected_revision=registry.REVISION_ZERO, actor='engineer')
    assert registry.read_state()['drafts'] == []


def test_requires_platform_auth_csrf_and_origin(isolated_registry):
    url='/api/pilot/platform/console/clinic-registry/drafts'
    with TestClient(app) as c:
        r=c.post(url,json=create_payload(registry.REVISION_ZERO))
        assert r.status_code in (401,403)
    with TestClient(app) as c:
        token=new_session('shanlin',role='clinic_admin',username='shanlin_admin')
        c.cookies.set(COOKIE, token, path='/api/pilot')
        assert c.post(url,json=create_payload(registry.REVISION_ZERO)).status_code==403
    with engineer_client() as c:
        csrf=c.get('/api/pilot/platform/console/session').json()['csrf']
        assert c.post(url, json=create_payload(registry.REVISION_ZERO),
                      headers={'Origin':'http://attacker.example', 'X-Pilot-CSRF':csrf}).status_code==403
        assert c.post(url, json=create_payload(registry.REVISION_ZERO),
                      headers={'Origin':'http://testserver'}).status_code==403
        assert c.post(url, json=create_payload(registry.REVISION_ZERO),
                      headers={'X-Pilot-CSRF':csrf}).status_code==403
        assert registry.read_state()['drafts']==[]


def test_api_stale_revision_is_http_409(isolated_registry):
    with engineer_client() as c:
        csrf=c.get('/api/pilot/platform/console/session').json()['csrf']
        headers={'Origin':'http://testserver','X-Pilot-CSRF':csrf}
        a=c.post('/api/pilot/platform/console/clinic-registry/drafts',json=create_payload(registry.REVISION_ZERO),headers=headers)
        assert a.status_code==200
        b=c.post('/api/pilot/platform/console/clinic-registry/drafts',json=create_payload(registry.REVISION_ZERO,'another-clinic'),headers=headers)
        assert b.status_code==409
        assert len(registry.read_state()['drafts'])==1
        edit=c.patch('/api/pilot/platform/console/clinic-registry/drafts/test-clinic',json={
            'displayName':'編輯後診所','notes':'','archived':False,
            'expectedRevision':a.json()['registry']['revision']},headers=headers)
        assert edit.status_code==200
        assert registry.read_state()['drafts'][0]['displayName']=='編輯後診所'


def test_external_client_blocked(isolated_registry):
    class External:
        def __init__(self, wrapped):self.wrapped=wrapped
        async def __call__(self, scope, receive, send):
            if scope['type']=='http':scope={**scope,'client':('203.0.113.9',12345)}
            await self.wrapped(scope,receive,send)
    with TestClient(External(app)) as c:
        assert c.get('/platform/clinics').status_code==403
        token = new_session(None, role='platform_admin', username='engineer_test')
        c.cookies.set(COOKIE, token, path='/api/pilot')
        assert c.get('/api/pilot/platform/console/clinic-registry').status_code==403


def test_no_preview_or_clinic_account_creation_from_new_draft(isolated_registry):
    s=registry.create_draft(clinic_id='north-clinic',display_name='北區示範診所',notes='',
                             expected_revision=registry.REVISION_ZERO,actor='engineer')
    assert all(d.get('readyForBooking') is False for d in s['drafts'])
    with TestClient(app) as c:
        # Unregistered clinics cannot leak Shanlin/Yidian data from public route.
        resp=c.get('/api/pilot/clinics/north-clinic/public')
        assert resp.status_code >= 400
