"""V3.2 dynamic module registry, security, migration and API integration."""
from pathlib import Path
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'website'))
from integrated_app_platform_v32 import app
import pilot_backend as backend
import platform_module_store_v32 as registry
import platform_console_store as legacy
import platform_clinic_registry as clinic_registry
import platform_onboarding_store_v3 as onboarding

API = '/api/pilot/platform/console/modules'
MID = 'ai_followup_reminder'
NEW = {'id': MID, 'name': 'AI 語音回診提醒', 'description': '未來以授權診所提醒回診。',
       'plannedVersion': '0.2.0', 'stage': 'planned'}

@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, '_paths', lambda: (tmp_path/'v32.json', tmp_path/'v32.lock'))
    monkeypatch.setattr(legacy, '_paths', lambda: (tmp_path/'v1.json', tmp_path/'v1.lock'))
    monkeypatch.setattr(clinic_registry, '_paths', lambda: (tmp_path/'v2.json', tmp_path/'v2.lock'))
    monkeypatch.setattr(onboarding, '_paths', lambda: (tmp_path/'v3.json', tmp_path/'v3.lock'))
    monkeypatch.setattr(backend, 'accounts_path', lambda: tmp_path/'accounts.json')
    registry.VERIFIED_RUNTIME_ADAPTERS.clear()
    backend._sessions.clear()
    backend._failed.clear()
    return tmp_path


def engineer():
    client=TestClient(app)
    token=backend.new_session(None,role='platform_admin',username='user')
    client.cookies.set(backend.COOKIE,token,path='/api/pilot')
    return client


def head(client):
    return {'Origin': 'http://testserver',
            'X-Pilot-CSRF': client.get('/api/pilot/platform/console/session').json()['csrf']}


def create(c, **overrides):
    body={**NEW,**overrides,'expectedRevision': c.get(API).json()['revision']}
    return c.post(API,json=body,headers=head(c))


def change(c, path, body, method='POST', revision=None):
    if revision is None:
        revision=c.get(API).json()['revision']
    return c.request(method,path,json={**body,'expectedRevision':revision},headers=head(c))


def add_draft():
    reg=clinic_registry.read_state()
    return clinic_registry.create_draft(clinic_id='third-demo',display_name='第三家示範診所',
                                        notes='',expected_revision=reg['revision'],actor='user')


def test_v32_page_and_assets_are_available_but_data_is_protected(isolated):
    with TestClient(app) as c:
        for path in ['/platform/admin','/platform/modules','/platform/assets/platform-v32.js',
                     '/platform/assets/module-center-v32.js','/platform/assets/module-center-v32.css']:
            assert c.get(path).status_code==200
        assert '工程師登入' in c.get('/platform/admin').text
        assert '功能模組管理中心' in c.get('/platform/modules').text
        for path in (API, API+'/audit'):
            assert c.get(path).status_code in (401,403)
        assert c.post(API,json={**NEW,'expectedRevision':registry.ZERO}).status_code in (401,403)
        assert "script-src 'self'" in c.get('/platform/modules').headers['content-security-policy']


def test_remote_browser_and_remote_api_refused(isolated):
    class Remote:
        def __init__(self, app): self.app=app
        async def __call__(self, scope, receive, send):
            if scope['type']=='http': scope={**scope,'client':('203.0.113.6',1234)}
            await self.app(scope,receive,send)
    with TestClient(Remote(app)) as c:
        assert c.get('/platform/modules').status_code==403
        assert c.get('/platform/admin').status_code==403
        token=backend.new_session(None, role='platform_admin',username='user')
        c.cookies.set(backend.COOKIE,token,path='/api/pilot')
        assert c.get(API).status_code==403


def test_clinic_admin_cannot_read_or_write_engineer_registry(isolated):
    with TestClient(app) as c:
        token=backend.new_session('shanlin', role='clinic_admin', username='shanlin_admin')
        c.cookies.set(backend.COOKIE, token, path='/api/pilot')
        assert c.get(API).status_code==403
        assert c.post(API,json={**NEW,'expectedRevision':registry.ZERO},headers={
            'Origin':'http://testserver','X-Pilot-CSRF':'x'}).status_code==403


def test_missing_csrf_and_cross_origin_rejected(isolated):
    with engineer() as c:
        body={**NEW,'expectedRevision':registry.ZERO}
        assert c.post(API,json=body).status_code==403
        assert c.post(API,json=body,headers={'Origin':'http://testserver'}).status_code==403
        assert c.post(API,json=body,headers={'Origin':'https://wrong.example','X-Pilot-CSRF':head(c)['X-Pilot-CSRF']}).status_code==403
        assert c.get(API).json()['revision']==registry.ZERO


def test_starts_with_three_previous_modules_and_disabled_runtime(isolated):
    state=registry.read_state()
    assert len(state['modules'])==3
    assert set(x['id'] for x in state['modules'])==set(legacy.FEATURES)
    assert set(c['id'] for c in state['clinics'])=={'shanlin','yidian'}
    assert all(x['deployment']=='not_deployed' for x in state['modules'])
    assert registry.clinic_entitlements('shanlin')['availableFeatures']==[]


def test_imports_legacy_flags_without_changing_file(isolated):
    legacy.update_flag(clinic='yidian',feature='ai_health_summary',enabled=True,
                       expected_revision=legacy.INITIAL_REVISION,actor='user')
    before=(isolated/'v1.json').read_bytes()
    with engineer() as c:
        assert c.get(API).json()['grants']['yidian']['ai_health_summary'] is True
        assert create(c).status_code==200
        assert c.get(API).json()['grants']['yidian']['ai_health_summary'] is True
    assert (isolated/'v1.json').read_bytes()==before


def test_v3_draft_is_loaded_and_its_existing_flags_migrate(isolated):
    add_draft()
    data=onboarding._default()
    item=onboarding._initial();item['features']['staff_worklist']=True
    data['clinics']['third-demo']=item
    onboarding._atomic(onboarding._paths()[0], data)
    state=registry.read_state()
    assert any(x['id']=='third-demo' and x['kind']=='draft' for x in state['clinics'])
    assert state['grants']['third-demo']['staff_worklist'] is True
    assert registry.clinic_entitlements('third-demo')['availableFeatures']==[]
    with engineer() as c:
        assert create(c).status_code==200
    assert (isolated/'v3.json').exists()
    assert (isolated/'v32.json').exists()


def test_create_edit_version_and_audit_as_real_actor(isolated):
    with engineer() as c:
        result=create(c)
        assert result.status_code==200,result.text
        state=result.json()['registry'];row=next(x for x in state['modules'] if x['id']==MID)
        assert row['name']==NEW['name'] and row['stage']=='planned'
        assert row['deployment']=='not_deployed'
        assert (isolated/'v32.json').exists()
        assert os.stat(isolated/'v32.json').st_mode & 0o777 == 0o600
        result=change(c,API+'/'+MID,{'name':'AI 回診智慧提醒',
          'description':'限診所工作者在本機測試。','plannedVersion':'1.2.0','stage':'testing'},method='PATCH')
        assert result.status_code==200,result.text
        changed=next(x for x in result.json()['registry']['modules'] if x['id']==MID)
        assert (changed['plannedVersion'],changed['stage'])==('1.2.0','testing')
        actions=c.get(API+'/audit').json()['entries']
        assert actions[0]['actor']=='user' and actions[0]['action']=='module_updated'
        assert actions[1]['action']=='module_created'


def test_duplicate_and_invalid_payload_rejected(isolated):
    with engineer() as c:
        assert create(c).status_code==200
        assert create(c).status_code==400
        assert create(c,id='bad-hyphen').status_code==422
        assert create(c,id='x').status_code==422
        assert create(c,plannedVersion='latest').status_code==400
        assert create(c,stage='deployed').status_code==422
        assert create(c,name=' ').status_code==422
        assert len(c.get(API).json()['modules'])==4


def test_revision_conflict_from_two_engineer_windows(isolated):
    with engineer() as c1, engineer() as c2:
        stale=c1.get(API).json()['revision']
        assert create(c2).status_code==200
        result=change(c1,API+'/'+MID+'/grants',{'clinicId':'shanlin','enabled':True},revision=stale)
        assert result.status_code==409
        assert c1.get(API).json()['grants']['shanlin'][MID] is False


def test_grants_for_existing_and_draft_clinics_are_independent(isolated):
    add_draft()
    with engineer() as c:
        assert create(c).status_code==200
        assert change(c,API+'/'+MID+'/grants',{'clinicId':'third-demo','enabled':True}).status_code==200
        assert change(c,API+'/'+MID+'/grants',{'clinicId':'shanlin','enabled':True}).status_code==200
        state=c.get(API).json()
        assert state['grants']['third-demo'][MID] is True
        assert state['grants']['shanlin'][MID] is True
        assert state['grants']['yidian'][MID] is False
        assert registry.clinic_entitlements('third-demo')['availableFeatures']==[]
        assert registry.clinic_entitlements('shanlin')['availableFeatures']==[]


def test_archived_clinic_cannot_be_newly_granted(isolated):
    add_draft()
    with engineer() as c:
        assert create(c).status_code==200
        old=clinic_registry.read_state()
        clinic_registry.update_draft(clinic_id='third-demo',display_name='第三家示範診所',
              notes='',archived=True,expected_revision=old['revision'],actor='user')
        assert change(c,API+'/'+MID+'/grants',{'clinicId':'third-demo','enabled':True}).status_code==400


def test_archiving_module_keeps_selection_but_blocks_future_grants(isolated):
    with engineer() as c:
        assert create(c).status_code==200
        assert change(c,API+'/'+MID+'/grants',{'clinicId':'shanlin','enabled':True}).status_code==200
        assert change(c,API+'/'+MID+'/lifecycle',{'archived':True}).status_code==200
        assert registry.clinic_entitlements('shanlin')['preauthorizedFeatures']==[]
        assert change(c,API+'/'+MID+'/grants',{'clinicId':'yidian','enabled':True}).status_code==400
        assert change(c,API+'/'+MID+'/lifecycle',{'archived':False}).status_code==200
        assert MID in registry.clinic_entitlements('shanlin')['preauthorizedFeatures']


def test_removed_draft_never_exposed_or_authorized_again(isolated):
    add_draft()
    with engineer() as c:
        assert create(c).status_code==200
        assert change(c,API+'/'+MID+'/grants',{'clinicId':'third-demo','enabled':True}).status_code==200
        # This test simulates safe V3.1 tombstoning after the draft was deleted.
        with clinic_registry._exclusive() as path:
            data=clinic_registry._load(path)
            del data['drafts']['third-demo']
            data['tombstones']['third-demo']={'actor':'user','deletedAt':'2026-10-24'}
            clinic_registry._write_atomic(path,data)
        state=c.get(API).json()
        assert 'third-demo' not in state['grants']
        assert all(t['id']!='third-demo' for t in state['clinics'])
        assert change(c,API+'/'+MID+'/grants',{'clinicId':'third-demo','enabled':False}).status_code==400


def test_old_static_mutation_endpoint_is_rejected_in_v32(isolated):
    with engineer() as c:
        r=c.post('/api/pilot/platform/console/features',headers=head(c),json={
            'clinicId':'shanlin','featureId':'staff_worklist','enabled':True,
            'expectedRevision':registry.ZERO})
        assert r.status_code==410


def test_public_clinic_entitlements_cannot_see_uninstalled_module(isolated):
    with engineer() as c:
        assert create(c).status_code==200
        assert change(c,API+'/'+MID+'/grants',{'clinicId':'shanlin','enabled':True}).status_code==200
    with TestClient(app) as c:
        token=backend.new_session('shanlin',role='clinic_admin',username='shanlin_admin')
        c.cookies.set(backend.COOKIE,token,path='/api/pilot')
        reply=c.get('/api/pilot/admin/platform-features')
        assert reply.status_code==200, reply.text
        assert MID in reply.json()['preauthorizedFeatures']
        assert reply.json()['availableFeatures']==[]


def test_fake_json_deployment_field_cannot_enable_executable_module(isolated):
    with engineer() as c:
        assert create(c).status_code==200
        assert change(c,API+'/'+MID+'/grants',{'clinicId':'shanlin','enabled':True}).status_code==200
        # Even if attacker/someone manually tampers with the operator JSON, the
        # runtime gate reads trusted source-code registrations, NOT the DB.
        path,_=registry._paths()
        data=json.loads(path.read_text('utf-8'))
        data['modules'][MID]['deployment']='deployed'
        registry._atomic(path,data)
        assert registry.clinic_entitlements('shanlin')['availableFeatures']==[]
        assert next(x for x in registry.read_state()['modules'] if x['id']==MID)['deployment']=='not_deployed'


def test_verified_runtime_only_effective_for_active_existing_tenant(isolated,monkeypatch):
    add_draft()
    with engineer() as c:
        assert create(c).status_code==200
        assert change(c,API+'/'+MID+'/grants',{'clinicId':'shanlin','enabled':True}).status_code==200
        assert change(c,API+'/'+MID+'/grants',{'clinicId':'third-demo','enabled':True}).status_code==200
    monkeypatch.setitem(registry.VERIFIED_RUNTIME_ADAPTERS,MID,
                        {'verified':True,'codeIntegrated':True,'version':'0.2.0'})
    assert MID in registry.clinic_entitlements('shanlin')['availableFeatures']
    assert registry.clinic_entitlements('third-demo')['availableFeatures']==[]
    monkeypatch.setitem(registry.VERIFIED_RUNTIME_ADAPTERS,MID,
                        {'verified':True,'codeIntegrated':False,'version':'0.2.0'})
    assert registry.clinic_entitlements('shanlin')['availableFeatures']==[]


def test_stored_module_data_does_not_include_sensitive_secret(isolated):
    with engineer() as c:
        assert create(c,description='僅屬於本機的示範說明').status_code==200
    raw=(isolated/'v32.json').read_text('utf-8')
    assert 'passwordHash' not in raw
    assert 'firebaseCredentials' not in raw
    assert 'patients' not in raw


def test_v32_onboarding_page_replaces_old_hardcoded_module_controls(isolated):
    add_draft()
    with TestClient(app) as c:
        page=c.get('/platform/clinics/third-demo/setup')
        assert page.status_code==200
        assert 'clinic-onboarding-v32.js' in page.text
        assert '功能模組授權管理（v3.2）' in page.text
        js=c.get('/platform/assets/clinic-onboarding-v32.js')
        assert js.status_code==200
        assert '功能模組管理中心' in js.text
        assert "data-feature=\"${esc(f.id)}\"" not in js.text
        assert c.get('/platform/clinics/shanlin/setup').status_code==404
    with engineer() as c:
        rev=onboarding.read('third-demo')['revision']
        res=c.post('/api/pilot/platform/console/onboarding/third-demo/features',
              headers=head(c),json={'featureId':'staff_worklist','enabled':True,'expectedRevision':rev})
        assert res.status_code==410


def test_v31_purge_on_v32_clears_dynamic_draft_grants(isolated):
    add_draft()
    with engineer() as c:
        assert create(c).status_code==200
        assert change(c,API+'/'+MID+'/grants',{'clinicId':'third-demo','enabled':True}).status_code==200
        current=clinic_registry.read_state()
        response=c.post('/api/pilot/platform/console/clinic-registry/drafts/third-demo/lifecycle',
          headers=head(c),json={'disabled':True,'expectedRevision':current['revision']})
        assert response.status_code==200,response.text
        check=c.get('/api/pilot/platform/console/clinic-registry/drafts/third-demo/deletion-check')
        assert check.status_code==200 and check.json()['canPurge'],check.text
        info=check.json()
        response=c.request('DELETE','/api/pilot/platform/console/clinic-registry/drafts/third-demo',
          json={'confirmation':'third-demo','expectedRegistryRevision':info['registryRevision'],
                'expectedOnboardingRevision':info['onboardingRevision']},headers=head(c))
        assert response.status_code==200,response.text
        assert response.json()['success']
        raw=json.loads((isolated/'v32.json').read_text('utf-8'))
        assert 'third-demo' not in raw['grants']
        assert any(a['action']=='deleted_draft_grants_purged' for a in raw['audit'])
        assert 'third-demo' not in c.get(API).json()['grants']
