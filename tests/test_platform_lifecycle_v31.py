"""V3.1 clinic disable and local-only staging purge, with hard safety barriers."""
from pathlib import Path
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'website'))
from integrated_app_platform_v31 import app
import pilot_backend as backend
import platform_clinic_registry as registry
import platform_onboarding_store_v3 as onboarding
import platform_lifecycle_store_v31 as lifecycle

SLUG='third-demo'
PREFIX='/api/pilot/platform/console/clinic-registry/drafts/'
STAGE='/api/pilot/platform/console/onboarding/' + SLUG
PASSWORD='LongStagingPassword_2026!'


@pytest.fixture
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(registry,'_paths',lambda:(tmp_path/'registry.json',tmp_path/'registry.lock'))
    monkeypatch.setattr(onboarding,'_paths',lambda:(tmp_path/'staging.json',tmp_path/'staging.lock'))
    monkeypatch.setattr(backend,'accounts_path',lambda:tmp_path/'accounts.json')
    monkeypatch.setattr(backend,'private_dir',lambda:tmp_path)
    backend._sessions.clear();backend._failed.clear()
    for prefix in ['PILOT_TENANT_THIRD_DEMO_', 'PILOT_TENANT_ANOTHER_DEMO_']:
        for suffix in ['FIREBASE_URL','FIREBASE_CREDENTIALS']:
            monkeypatch.delenv(prefix+suffix,raising=False)
    registry.create_draft(clinic_id=SLUG,display_name='第三家示範診所',notes='測試備註',
                          expected_revision=registry.REVISION_ZERO,actor='user')
    return tmp_path


def engineer():
    client=TestClient(app)
    token=backend.new_session(None,role='platform_admin',username='user')
    client.cookies.set(backend.COOKIE,token,path='/api/pilot')
    return client


def headers(client):
    s=client.get('/api/pilot/platform/console/session').json()
    return {'Origin':'http://testserver','X-Pilot-CSRF':s['csrf']}


def patch_state(client,slug=SLUG,disabled=True,revision=None):
    if revision is None:
        revision=registry.read_state()['revision']
    return client.post(PREFIX+slug+'/lifecycle',json={
        'disabled':disabled,'expectedRevision':revision},headers=headers(client))


def delete(client,slug=SLUG,confirmation=SLUG,revision=None,stage_rev=None):
    if revision is None:
        revision=registry.read_state()['revision']
    if stage_rev is None:
        stage_rev=onboarding._load(onboarding._paths()[0])['revision']
    return client.request('DELETE',PREFIX+slug,json={
        'confirmation':confirmation,'expectedRegistryRevision':revision,
        'expectedOnboardingRevision':stage_rev},headers=headers(client))


def create_account(client):
    revision=onboarding._load(onboarding._paths()[0])['revision']
    return client.post(STAGE+'/account',json={
        'username':'third_admin','password':PASSWORD,'reset':False,
        'expectedRevision':revision},headers=headers(client))


def assert_absent():
    assert not any(d['clinicId']==SLUG for d in registry.read_state()['drafts'])


def test_v31_routes_and_console_ui_render(isolated):
    with engineer() as c:
        r=c.get('/platform/clinics')
        assert r.status_code==200
        assert 'deletePanel' in r.text
        js=c.get('/platform/assets/clinic-center.js')
        assert 'data-purge' in js.text and 'data-lifecycle' in js.text
        assert c.get('/platform/clinics/'+SLUG+'/setup').status_code==200
        check=c.get(PREFIX+SLUG+'/deletion-check')
        assert check.status_code==200 and check.json()['canPurge'] is False
        assert '請先停用' in check.json()['blockers'][0]


def test_reversible_disable_preserves_draft_and_revokes_local_sessions(isolated):
    with engineer() as c:
        assert create_account(c).status_code==200
        token=backend.new_session(SLUG,role='onboarding_admin',username='third_admin')
        digest=backend.sha256(token.encode()).hexdigest()
        assert digest in backend._sessions
        r=patch_state(c)
        assert r.status_code==200,r.text
        assert r.json()['registry']['drafts'][0]['archived'] is True
        assert digest not in backend._sessions
        assert onboarding.check_account(SLUG,username='third_admin',password=PASSWORD) is False
        assert c.get(STAGE).json()['readyForProduction'] is False
        r=patch_state(c,disabled=False)
        assert r.status_code==200
        assert onboarding.check_account(SLUG,username='third_admin',password=PASSWORD) is True
        assert backend._sessions.get(digest) is None
        assert c.get(STAGE).json()['readyForBooking'] is False


def test_can_delete_plain_draft_after_disable_and_cannot_reuse_slug(isolated):
    with engineer() as c:
        assert delete(c).status_code==409
        assert patch_state(c).status_code==200
        check=c.get(PREFIX+SLUG+'/deletion-check').json()
        assert check['canPurge'] is True
        out=delete(c)
        assert out.status_code==200,out.text
        assert out.json()['success'] is True
        assert_absent()
        assert 'third-demo' in registry._load(registry._paths()[0])['tombstones']
        assert registry.audit_tail()[0]['action']=='draft_permanently_deleted'
        assert '第三家示範診所' not in (isolated/'registry.json').read_text('utf-8')
        assert '測試備註' not in (isolated/'registry.json').read_text('utf-8')
        again=c.post('/api/pilot/platform/console/clinic-registry/drafts',json={
            'clinicId':SLUG,'displayName':'不應重建','notes':'',
            'expectedRevision':registry.read_state()['revision']},headers=headers(c))
        assert again.status_code==400 and '不能重複使用' in again.text
        assert delete(c).status_code in (400,409)


def test_delete_staging_account_and_profile_are_removed_and_sessions_invalidated(isolated):
    with engineer() as c:
        assert create_account(c).status_code==200
        rev=onboarding._load(onboarding._paths()[0])['revision']
        r=c.post(STAGE+'/profile',json={'phone':'02-2222-3333','address':'示範地址',
                                       'hours':'週一','expectedRevision':rev},headers=headers(c))
        assert r.status_code==200
        token=backend.new_session(SLUG,role='onboarding_admin',username='third_admin')
        digest=backend.sha256(token.encode()).hexdigest()
        assert patch_state(c).status_code==200
        assert delete(c).status_code==200
        assert SLUG not in onboarding._load(onboarding._paths()[0])['clinics']
        assert PASSWORD not in (isolated/'staging.json').read_text('utf-8')
        assert 'third_admin' not in (isolated/'staging.json').read_text('utf-8')
        assert '示範地址' not in (isolated/'staging.json').read_text('utf-8')
        assert digest not in backend._sessions
        assert c.get(STAGE).status_code==404


def test_delete_requires_exact_confirmation_and_revision(isolated):
    with engineer() as c:
        assert patch_state(c).status_code==200
        assert delete(c,confirmation='another-demo').status_code==409
        assert delete(c,revision=registry.REVISION_ZERO).status_code==409
        assert delete(c,stage_rev='e'*32).status_code==409
        assert len(registry.read_state()['drafts'])==1
        assert delete(c).status_code==200


def test_delete_prevented_when_storage_intent_set(isolated):
    with engineer() as c:
        rev=onboarding._load(onboarding._paths()[0])['revision']
        assert c.post(STAGE+'/storage',json={'mode':'firebase_rtdb','expectedRevision':rev},headers=headers(c)).status_code==200
        assert patch_state(c).status_code==200
        data=c.get(PREFIX+SLUG+'/deletion-check').json()
        assert data['canPurge'] is False
        assert 'Firebase' in ' '.join(data['blockers'])
        assert delete(c).status_code==409
        assert len(registry.read_state()['drafts'])==1


def test_delete_prevented_for_actual_configured_env_even_if_unconfigured(isolated,monkeypatch):
    with engineer() as c:
        assert patch_state(c).status_code==200
        monkeypatch.setenv('PILOT_TENANT_THIRD_DEMO_FIREBASE_URL','https://third-default-rtdb.firebaseio.com')
        assert delete(c).status_code==409
        monkeypatch.delenv('PILOT_TENANT_THIRD_DEMO_FIREBASE_URL')
        monkeypatch.setenv('PILOT_TENANT_THIRD_DEMO_FIREBASE_CREDENTIALS','dummy-test-secret')
        assert delete(c).status_code==409
        assert 'dummy-test-secret' not in c.get(PREFIX+SLUG+'/deletion-check').text


def test_delete_prevented_for_pending_or_any_prior_review(isolated):
    with engineer() as c:
        with onboarding._exclusive() as path:
            data=onboarding._load(path)
            data['clinics'][SLUG]=onboarding._initial()
            data['clinics'][SLUG]['reviewState']='pending_review'
            data['revision']='e'*32
            onboarding._atomic(path,data)
        assert patch_state(c).status_code==200
        assert delete(c).status_code==409
        with onboarding._exclusive() as path:
            data=onboarding._load(path)
            data['clinics'][SLUG]['reviewState']='draft'
            data['audit'].append({'clinicId':SLUG,'action':'submitted_for_review','actor':'user'})
            data['revision']='f'*32
            onboarding._atomic(path,data)
        assert delete(c).status_code==409


def test_existing_real_clinics_protected_no_mutation(isolated):
    with engineer() as c:
        for slug in ('shanlin','yidian','platform','admin'):
            assert patch_state(c,slug).status_code==400
            assert delete(c,slug,confirmation=slug).status_code==400
            assert c.get(PREFIX+slug+'/deletion-check').status_code==404
        assert len(registry.read_state()['drafts'])==1


def test_other_draft_unchanged(isolated):
    registry.create_draft(clinic_id='another-demo',display_name='另一家示範',notes='其他',
                          expected_revision=registry.read_state()['revision'],actor='user')
    with engineer() as c:
        assert patch_state(c).status_code==200
        assert delete(c).status_code==200
        other=registry.read_state()['drafts']
        assert len(other)==1 and other[0]['clinicId']=='another-demo'
        assert other[0]['notes']=='其他'


def test_engineer_auth_csrf_origin_and_clinic_roles(isolated):
    url=PREFIX+SLUG+'/lifecycle'
    body={'disabled':True,'expectedRevision':registry.read_state()['revision']}
    with TestClient(app) as c:
        assert c.post(url,json=body).status_code in (401,403)
        assert c.request('DELETE',PREFIX+SLUG,json={}).status_code in (401,403)
        assert c.get(PREFIX+SLUG+'/deletion-check').status_code in (401,403)
    with TestClient(app) as c:
        cookie=backend.new_session('shanlin',role='clinic_admin',username='shanlin_admin')
        c.cookies.set(backend.COOKIE,cookie,path='/api/pilot')
        assert c.post(url,json=body).status_code==403
        assert c.get(PREFIX+SLUG+'/deletion-check').status_code==403
    with engineer() as c:
        assert c.post(url,json=body).status_code==403
        assert c.post(url,json=body,headers={'Origin':'http://evil.example'}).status_code==403
        assert c.post(url,json=body,headers={'Origin':'http://testserver'}).status_code==403
        assert c.request('DELETE',PREFIX+SLUG,json={
            'confirmation':SLUG,'expectedRegistryRevision':registry.read_state()['revision'],
            'expectedOnboardingRevision':onboarding.ZERO},headers={'Origin':'http://testserver'}).status_code==403
        assert registry.read_state()['drafts'][0]['archived'] is False


def test_nonlocal_denied(isolated):
    class Remote:
        def __init__(self, app):self.app=app
        async def __call__(self, scope, receive, send):
            if scope['type']=='http':scope={**scope,'client':('203.0.113.90',50000)}
            return await self.app(scope,receive,send)
    with TestClient(Remote(app)) as c:
        tok=backend.new_session(None,role='platform_admin',username='user')
        c.cookies.set(backend.COOKIE,tok,path='/api/pilot')
        assert c.get(PREFIX+SLUG+'/deletion-check').status_code==403
        assert c.post(PREFIX+SLUG+'/lifecycle',json={}).status_code==403


def test_delete_stays_safe_after_cross_file_write_error(isolated,monkeypatch):
    with engineer() as c:
        assert create_account(c).status_code==200
        assert patch_state(c).status_code==200
        original=registry._write_atomic
        def fail(*args,**kwargs):raise OSError('simulated disk failure')
        monkeypatch.setattr(registry,'_write_atomic',fail)
        with pytest.raises(OSError):delete(c)
        monkeypatch.setattr(registry,'_write_atomic',original)
        assert len(registry.read_state()['drafts'])==1
        assert SLUG not in onboarding._load(onboarding._paths()[0])['clinics']
        # Refreshed revisions permit safe retry after data layer recovered.
        assert delete(c).status_code==200


def test_deleted_data_is_local_and_existing_files_untouched(isolated):
    other=isolated/'shanlin-real-data.json'
    other.write_text('DO NOT TOUCH',encoding='utf-8')
    with engineer() as c:
        assert patch_state(c).status_code==200
        assert delete(c).status_code==200
    assert other.read_text('utf-8')=='DO NOT TOUCH'
    assert (isolated/'registry.json').stat().st_mode&0o777==0o600
    assert SLUG in json.loads((isolated/'registry.json').read_text('utf-8'))['tombstones']


def test_old_schema_without_tombstones_is_migrated_non_destructively(isolated):
    path=registry._paths()[0]
    data=json.loads(path.read_text('utf-8'))
    data.pop('tombstones',None)
    path.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    with engineer() as c:
        assert patch_state(c).status_code==200
        assert delete(c).status_code==200
    assert_absent()


def test_invalid_staging_schema_cannot_delete_v2(isolated):
    stage_path=onboarding._paths()[0]
    stage_path.write_text('{"bad":true}',encoding='utf-8')
    with engineer() as c:
        assert patch_state(c).status_code==200
        with pytest.raises(RuntimeError):delete(c)
        assert len(registry.read_state()['drafts'])==1
