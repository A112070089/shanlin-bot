"""V3 staging onboarding isolation/auth/password/revision/activation tests."""
from pathlib import Path
from collections import defaultdict, deque
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'website'))
from integrated_app_platform_v3 import app
import pilot_backend as backend
import platform_clinic_registry as registry
import platform_onboarding_store_v3 as store

SLUG = 'third-demo'
BASE = '/api/pilot/platform/console/onboarding/' + SLUG
PWD = 'VeryLongDemoPass_2026!'


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, '_paths', lambda: (tmp_path/'v2.json', tmp_path/'v2.lock'))
    monkeypatch.setattr(store, '_paths', lambda: (tmp_path/'v3.json', tmp_path/'v3.lock'))
    monkeypatch.setattr(backend, 'accounts_path', lambda: tmp_path/'accounts.json')
    backend._sessions.clear()
    backend._failed.clear()
    for suffix in ('FIREBASE_URL', 'FIREBASE_CREDENTIALS'):
        monkeypatch.delenv('PILOT_TENANT_THIRD_DEMO_'+suffix, raising=False)
    monkeypatch.delenv('PILOT_SHANLIN_FIREBASE_URL', raising=False)
    monkeypatch.delenv('PILOT_YIDIAN_FIREBASE_URL', raising=False)
    monkeypatch.delenv('FIREBASE_URL', raising=False)
    registry.create_draft(clinic_id=SLUG,display_name='第三家示範診所',notes='',
                          expected_revision=registry.REVISION_ZERO,actor='user')
    return tmp_path


def engineer():
    c=TestClient(app)
    token=backend.new_session(None, role='platform_admin', username='user')
    c.cookies.set(backend.COOKIE, token, path='/api/pilot')
    return c


def head(client):
    return {'Origin':'http://testserver',
            'X-Pilot-CSRF':client.get('/api/pilot/platform/console/session').json()['csrf']}


def save(client, postfix, data):
    state=client.get(BASE).json()
    return client.post(BASE+postfix, json={**data,'expectedRevision':state['revision']},
                       headers=head(client))


def account(c, reset=False, username='third_admin', password=PWD):
    return save(c, '/account', {'username':username,'password':password,'reset':reset})


def profile(c):
    return save(c, '/profile', {'phone':'02-1234-5678',
                                'address':'臺北市示範路 100 號',
                                'hours':'週一至週五 09:00-18:00'})


def test_v3_page_and_existing_v2_remain_accessible(isolated):
    with TestClient(app) as c:
        assert c.get(f'/platform/clinics/{SLUG}/setup').status_code == 200
        assert '新診所開通準備' in c.get(f'/platform/clinics/{SLUG}/setup').text
        assert c.get('/platform/clinics/shanlin/setup').status_code == 404
        assert c.get('/platform/clinics/nonexistent/setup').status_code == 404
        assert c.get('/platform/clinics').status_code == 200
        for path in ('/platform/assets/clinic-onboarding-v3.js',
                     '/platform/assets/clinic-onboarding-v3.css',
                     '/platform/clinic-onboarding-login',
                     '/platform/assets/clinic-onboarding-login-v3.js'):
            assert c.get(path).status_code == 200


def test_account_provision_stores_only_hash_and_no_patient_data(isolated):
    with engineer() as c:
        assert account(c).status_code == 200
        state=c.get(BASE).json()
        assert state['account']['created']
        assert state['account']['username']=='third_admin'
        assert 'passwordHash' not in json.dumps(state)
        contents=(isolated/'v3.json').read_text('utf-8')
        assert PWD not in contents
        assert 'passwordHash' in contents
        assert os.stat(isolated/'v3.json').st_mode & 0o777 == 0o600
        assert 'third_admin' in contents
        assert store.check_account(SLUG,username='third_admin',password=PWD)
        assert not store.check_account(SLUG,username='another',password=PWD)
        assert not store.check_account(SLUG,username='third_admin',password='bad')


def test_account_requires_explicit_rotation_and_invalidates_session(isolated):
    with engineer() as c:
        assert account(c).status_code==200
        assert account(c).status_code==400
        session=backend.new_session(SLUG,role='onboarding_admin',username='third_admin')
        assert backend.sha256(session.encode()).hexdigest() in backend._sessions
        assert account(c,reset=True,password='AnotherLongPass_2027!').status_code==200
        assert backend.sha256(session.encode()).hexdigest() not in backend._sessions
        assert not store.check_account(SLUG,username='third_admin',password=PWD)
        assert store.check_account(SLUG,username='third_admin',password='AnotherLongPass_2027!')


def test_usernames_are_unique_and_reserved_across_clinics(isolated):
    with engineer() as c:
        for username in ('shanlin_admin','yidian_admin','platform_admin'):
            assert account(c,username=username).status_code==400
        assert account(c).status_code==200
        rev=registry.read_state()['revision']
        registry.create_draft(clinic_id='another-demo',display_name='另一示範診所',notes='',
                              expected_revision=rev,actor='user')
        state=c.get('/api/pilot/platform/console/onboarding/another-demo').json()
        r=c.post('/api/pilot/platform/console/onboarding/another-demo/account',json={
            'username':'third_admin','password':PWD,'reset':False,'expectedRevision':state['revision']},
            headers=head(c))
        assert r.status_code==400


def test_enforce_platform_auth_csrf_origin_and_tenant_isolation(isolated):
    with TestClient(app) as c:
        assert c.get(BASE).status_code in (401,403)
        assert c.post(BASE+'/account',json={}).status_code in (401,403)
    with TestClient(app) as c:
        token=backend.new_session('shanlin',role='clinic_admin',username='shanlin_admin')
        c.cookies.set(backend.COOKIE,token,path='/api/pilot')
        assert c.get(BASE).status_code==403
    with engineer() as c:
        rev=c.get(BASE).json()['revision']
        body={'username':'third_admin','password':PWD,'reset':False,'expectedRevision':rev}
        assert c.post(BASE+'/account',json=body).status_code==403
        assert c.post(BASE+'/account',json=body,headers={'Origin':'http://evil.example'}).status_code==403
        assert c.post(BASE+'/account',json=body,headers={'Origin':'http://testserver'}).status_code==403
        assert c.get('/api/pilot/platform/console/onboarding/yidian').status_code==404
        assert c.get('/api/pilot/platform/console/onboarding/shanlin').status_code==404
        assert not store.read(SLUG)['account']['created']


def test_nonlocal_access_forbidden_even_with_engineer_session(isolated):
    class Remote:
        def __init__(self, inner):self.inner=inner
        async def __call__(self, scope, receive, send):
            if scope['type']=='http':scope={**scope,'client':('203.0.113.20',52820)}
            await self.inner(scope,receive,send)
    with TestClient(Remote(app)) as c:
        assert c.get(f'/platform/clinics/{SLUG}/setup').status_code==403
        token=backend.new_session(None,role='platform_admin',username='user')
        c.cookies.set(backend.COOKIE,token,path='/api/pilot')
        assert c.get(BASE).status_code==403


def test_firebase_env_is_presence_only_never_connected(isolated, monkeypatch):
    with engineer() as c:
        state=c.get(BASE).json()
        assert state['storage']['configurationPresent'] is False
        r=save(c,'/storage',{'mode':'firebase_rtdb'})
        assert r.status_code==200
        monkeypatch.setenv('PILOT_TENANT_THIRD_DEMO_FIREBASE_URL','https://third-clinic-default-rtdb.asia-southeast1.firebasedatabase.app')
        monkeypatch.setenv('PILOT_TENANT_THIRD_DEMO_FIREBASE_CREDENTIALS','testing-env-secret-not-real')
        state=c.get(BASE).json()
        assert state['storage']['configurationPresent'] is True
        assert state['storage']['connectionVerified'] is False
        assert 'testing-env-secret-not-real' not in json.dumps(state)
        monkeypatch.setenv('PILOT_SHANLIN_FIREBASE_URL','https://third-clinic-default-rtdb.asia-southeast1.firebasedatabase.app')
        assert c.get(BASE).json()['storage']['configurationPresent'] is False
        monkeypatch.setenv('PILOT_TENANT_THIRD_DEMO_FIREBASE_URL','http://localhost:8000')
        assert c.get(BASE).json()['storage']['urlFormatValid'] is False


def test_cannot_submit_review_until_profile_account_env_complete(isolated,monkeypatch):
    with engineer() as c:
        assert save(c,'/review',{}).status_code==400
        assert profile(c).status_code==200
        assert account(c).status_code==200
        assert save(c,'/storage',{'mode':'firebase_rtdb'}).status_code==200
        assert save(c,'/review',{}).status_code==400
        monkeypatch.setenv('PILOT_TENANT_THIRD_DEMO_FIREBASE_URL','https://third-clinic-default-rtdb.firebaseio.com')
        monkeypatch.setenv('PILOT_TENANT_THIRD_DEMO_FIREBASE_CREDENTIALS','testing-env-secret-not-real')
        ready=c.get(BASE).json()
        assert ready['maySubmitForReview'] is True
        assert ready['readyForBooking'] is False
        assert ready['readyForProduction'] is False
        r=save(c,'/review',{})
        assert r.status_code==200
        assert r.json()['reviewState']=='pending_review'
        assert r.json()['readyForBooking'] is False
        assert save(c,'/features',{'featureId':'ai_health_summary','enabled':True}).status_code==200
        state=c.get(BASE).json()
        assert state['reviewState']=='draft'
        assert next(f for f in state['features'] if f['id']=='ai_health_summary')['enabled'] is True
        assert next(f for f in state['features'] if f['id']=='ai_health_summary')['deployed'] is False


def test_staging_login_isolated_no_booking_or_engineer_access(isolated):
    with engineer() as c:
        assert account(c).status_code==200
    with TestClient(app) as client:
        headers={'Origin':'http://testserver'}
        body={'clinicId':SLUG,'username':'third_admin','password':PWD}
        assert client.post('/api/pilot/onboarding/login',json=body).status_code==403
        assert client.post('/api/pilot/onboarding/login',json={**body,'username':'bad_user'},headers=headers).status_code==401
        r=client.post('/api/pilot/onboarding/login',json=body,headers=headers)
        assert r.status_code==200
        assert r.json()['role']=='onboarding_admin'
        sess=client.get('/api/pilot/onboarding/session')
        assert sess.status_code==200 and sess.json()['clinicId']==SLUG
        assert client.get('/api/pilot/platform/console/state').status_code==403
        assert client.get('/api/pilot/platform/console/clinic-registry').status_code==403
        assert client.get('/api/pilot/admin/state').status_code==403
        assert client.get('/api/pilot/clinics/shanlin/public').status_code==200  # only public catalog
        assert client.post('/api/pilot/clinics/third-demo/demo-booking',json={}).status_code in (404,410,422)


def test_stale_revision_and_archived_draft_cannot_mutate_or_login(isolated):
    with engineer() as a, engineer() as b:
        rev=a.get(BASE).json()['revision']
        assert profile(a).status_code==200
        body={'mode':'firebase_rtdb','expectedRevision':rev}
        assert b.post(BASE+'/storage',json=body,headers=head(b)).status_code==409
        archived=registry.update_draft(clinic_id=SLUG,display_name='第三家示範診所',notes='',
            archived=True,expected_revision=registry.read_state()['revision'],actor='user')
        assert archived['drafts'][0]['archived'] is True
        assert profile(a).status_code==400
        assert account(a).status_code==400
        assert not store.check_account(SLUG,username='third_admin',password=PWD)


def test_no_release_routes_and_no_secret_echo(isolated):
    with engineer() as c:
        assert account(c).status_code==200
        state=c.get(BASE).json()
        assert state['readyForBooking'] is False
        assert state['readyForProduction'] is False
        assert c.post(BASE+'/activate',json={},headers=head(c)).status_code==404
        assert 'passwordHash' not in json.dumps(state)
        tail=c.get(BASE+'/audit').json()['entries']
        assert tail[0]['actor']=='user'
        assert all('password' not in json.dumps(item).lower() for item in tail)
