"""v3.2.1 global plan, historical mapping diagnostics, and safety checks."""
from pathlib import Path
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'website'))
from integrated_app_platform_v321 import app
import pilot_backend as backend
import platform_console_store as v1
import platform_module_store_v32 as v32
import platform_standard_policy_v321 as plan
import platform_clinic_registry as clinics
import platform_onboarding_store_v3 as onboarding

API='/api/pilot/platform/console/modules'
MID='ai_standard_followup'
NEW={'id':MID,'name':'AI 回診通知規劃','description':'僅本機演示','plannedVersion':'0.1.0','stage':'planned'}

@pytest.fixture
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(plan,'_paths',lambda:(tmp_path/'global.json',tmp_path/'global.lock'))
    monkeypatch.setattr(v32,'_paths',lambda:(tmp_path/'v32.json',tmp_path/'v32.lock'))
    monkeypatch.setattr(v1,'_paths',lambda:(tmp_path/'v1.json',tmp_path/'v1.lock'))
    monkeypatch.setattr(clinics,'_paths',lambda:(tmp_path/'v2.json',tmp_path/'v2.lock'))
    monkeypatch.setattr(onboarding,'_paths',lambda:(tmp_path/'v3.json',tmp_path/'v3.lock'))
    monkeypatch.setattr(backend,'accounts_path',lambda:tmp_path/'accounts.json')
    monkeypatch.setattr(plan,'VERIFIED_LIVE_CLINICS',frozenset())
    v32.VERIFIED_RUNTIME_ADAPTERS.clear()
    backend._sessions.clear();backend._failed.clear()
    return tmp_path

def admin():
    client=TestClient(app)
    token=backend.new_session(None,role='platform_admin',username='user')
    client.cookies.set(backend.COOKIE,token,path='/api/pilot')
    return client

def csrf(client):
    return {'Origin':'http://testserver',
            'X-Pilot-CSRF':client.get('/api/pilot/platform/console/session').json()['csrf']}

def include(client,mid,enabled=True,rev=None):
    if rev is None:rev=client.get(API).json()['policyRevision']
    return client.post(API+'/'+mid+'/standard',json={'enabled':enabled,'expectedPolicyRevision':rev},
                       headers=csrf(client))

def add(client):
    rev=client.get(API).json()['revision']
    return client.post(API,json={**NEW,'expectedRevision':rev},headers=csrf(client))


def test_global_ui_replaces_per_clinic_checkboxes(isolated):
    with TestClient(app) as c:
        assert c.get('/platform/modules').status_code==200
        page=c.get('/platform/modules').text
        assert 'module-center-v321.js' in page
        assert '所有已正式開通的診所共同適用' in page
        js=c.get('/platform/assets/module-center-v321.js').text
        assert 'data-standard=' in js and '納入共用標準版' in js
        assert 'data-clinic=' not in js and 'toggleGrant' not in js
        assert c.get('/platform/admin').status_code==200
        assert 'platform-v321.js' in c.get('/platform/admin').text
        assert "script-src 'self'" in c.get('/platform/modules').headers['content-security-policy']


def test_no_automatic_promotion_of_old_individual_selection(isolated):
    v1.update_flag(clinic='yidian',feature='ai_health_summary',enabled=True,
                   expected_revision=v1.INITIAL_REVISION,actor='user')
    before=(isolated/'v1.json').read_bytes()
    with admin() as c:
        state=c.get(API).json()
        assert not next(m for m in state['modules'] if m['id']=='ai_health_summary')['standardIncluded']
        assert include(c,'ai_health_summary').status_code==200
        assert next(m for m in c.get(API).json()['modules'] if m['id']=='ai_health_summary')['standardIncluded']
    assert (isolated/'v1.json').read_bytes()==before
    assert 'grants' not in json.loads((isolated/'global.json').read_text())


def test_v1_v32_mismatch_report_by_real_clinic_id_not_order(isolated):
    v1.update_flag(clinic='yidian',feature='ai_health_summary',enabled=True,
                   expected_revision=v1.INITIAL_REVISION,actor='user')
    # Persist v3.2 with a DIFFERENT human choice, without changing v1.
    v32.set_grant(module_id='ai_health_summary',clinic_id='shanlin',enabled=True,
                  expected_revision=v32.ZERO,actor='user')
    with admin() as c:
        report=c.get(API+'/migration').json()
        rows={(x['clinicId'],x['moduleId']):x for x in report['differences']}
        assert ('shanlin','ai_health_summary') in rows
        assert report['historical'][0]['v1Flags']['yidian'] is True
        assert report['historical'][0]['v32Flags']['shanlin'] is True
        assert report['differenceCount']>=1
        assert c.get(API).json()['historicalCheck']['differenceCount']==report['differenceCount']
    assert not (isolated/'global.json').exists()  # read-only checking


def test_one_global_switch_automatically_applies_to_both_clinics(isolated):
    with admin() as c:
        assert include(c,'staff_worklist').status_code==200
        state=c.get(API).json()
        assert state['scope']=='all_activated_clinics_same_standard_plan'
        assert 'staff_worklist' in state['standardModuleIds']
        y=plan.clinic_entitlements('yidian')
        s=plan.clinic_entitlements('shanlin')
        assert y['standardPlanFeatures']==s['standardPlanFeatures']
        assert y['preauthorizedFeatures']==s['preauthorizedFeatures']==['staff_worklist']
        assert y['availableFeatures']==s['availableFeatures']==[]
        assert include(c,'staff_worklist',False).status_code==200
        assert plan.clinic_entitlements('yidian')['standardPlanFeatures']==[]
        assert plan.clinic_entitlements('shanlin')['standardPlanFeatures']==[]


def test_new_module_is_not_globally_enabled_until_engineer_selects_it(isolated):
    with admin() as c:
        assert add(c).status_code==200
        m=next(row for row in c.get(API).json()['modules'] if row['id']==MID)
        assert m['standardIncluded'] is False
        assert m['releaseStatus']=='未納入標準版'
        assert include(c,MID).status_code==200
        assert MID in plan.clinic_entitlements('shanlin')['standardPlanFeatures']
        assert MID in plan.clinic_entitlements('yidian')['standardPlanFeatures']
        assert MID not in plan.clinic_entitlements('shanlin')['availableFeatures']


def test_draft_may_see_plan_but_never_reaches_clinical_api(isolated):
    reg=clinics.read_state()
    clinics.create_draft(clinic_id='third-demo',display_name='第三家示範診所',notes='',
                         expected_revision=reg['revision'],actor='user')
    with admin() as c:
        assert include(c,'ai_health_summary').status_code==200
        state=c.get(API).json()
        assert next(x for x in state['clinics'] if x['id']=='third-demo')['canUseClinicalModules'] is False
        draft=plan.clinic_entitlements('third-demo')
        assert draft['standardPlanFeatures']==['ai_health_summary']
        assert draft['preauthorizedFeatures']==draft['availableFeatures']==[]
    reg=clinics.read_state()
    clinics.update_draft(clinic_id='third-demo',display_name='第三家示範診所',notes='',
                         archived=True,expected_revision=reg['revision'],actor='user')
    assert plan.clinic_entitlements('third-demo')['availableFeatures']==[]


def test_existing_clinic_same_policy_but_requires_verified_runtime_and_onboarding(isolated,monkeypatch):
    with admin() as c:
        assert add(c).status_code==200
        assert include(c,MID).status_code==200
    monkeypatch.setitem(v32.VERIFIED_RUNTIME_ADAPTERS,MID,
                        {'verified':True,'codeIntegrated':True,'version':'0.1.0'})
    assert plan.clinic_entitlements('shanlin')['availableFeatures']==[]
    assert plan.clinic_entitlements('yidian')['availableFeatures']==[]
    monkeypatch.setattr(plan,'VERIFIED_LIVE_CLINICS',frozenset({'shanlin'}))
    assert plan.clinic_entitlements('shanlin')['availableFeatures']==[MID]
    assert plan.clinic_entitlements('yidian')['availableFeatures']==[]  # Demo not clinically live


def test_fake_json_status_does_not_make_uninstalled_program_live(isolated,monkeypatch):
    with admin() as c:
        assert add(c).status_code==200
        assert include(c,MID).status_code==200
    data=json.loads((isolated/'v32.json').read_text())
    data['modules'][MID]['deployment']='deployed'
    v32._atomic(isolated/'v32.json',data)
    monkeypatch.setattr(plan,'VERIFIED_LIVE_CLINICS',frozenset({'shanlin'}))
    assert plan.clinic_entitlements('shanlin')['availableFeatures']==[]
    assert next(m for m in plan.read_state()['modules'] if m['id']==MID)['deployment']=='not_deployed'


def test_old_grant_endpoints_retired_even_if_authorized(isolated):
    with admin() as c:
        assert c.post(API+'/ai_health_summary/grants',json={'clinicId':'shanlin','enabled':True,'expectedRevision':v32.ZERO},
                      headers=csrf(c)).status_code==410
        assert c.post('/api/pilot/platform/console/features',json={},headers=csrf(c)).status_code==410
        assert c.post('/api/pilot/platform/console/onboarding/third-demo/features',json={},
                      headers=csrf(c)).status_code==410


def test_must_be_engineer_and_same_origin_with_csrf(isolated):
    with TestClient(app) as c:
        assert c.get(API).status_code in (401,403)
        assert c.post(API+'/ai_health_summary/standard',json={'enabled':True,'expectedPolicyRevision':plan.ZERO}).status_code in (401,403)
        token=backend.new_session('shanlin',role='clinic_admin',username='shanlin_admin')
        c.cookies.set(backend.COOKIE,token,path='/api/pilot')
        assert c.get(API).status_code==403
    with admin() as c:
        payload={'enabled':True,'expectedPolicyRevision':plan.ZERO}
        assert c.post(API+'/ai_health_summary/standard',json=payload).status_code==403
        assert c.post(API+'/ai_health_summary/standard',json=payload,headers={
            'Origin':'https://evil.example','X-Pilot-CSRF':csrf(c)['X-Pilot-CSRF']}).status_code==403
        assert c.get(API).json()['standardModuleIds']==[]


def test_policy_revision_conflict_when_two_engineer_tabs_edit(isolated):
    with admin() as c1,admin() as c2:
        old=c1.get(API).json()['policyRevision']
        assert include(c2,'staff_worklist').status_code==200
        result=include(c1,'ai_health_summary',rev=old)
        assert result.status_code==409
        assert c1.get(API).json()['standardModuleIds']==['staff_worklist']


def test_archived_module_cannot_be_added_and_existing_plan_temporarily_suppressed(isolated):
    with admin() as c:
        assert add(c).status_code==200
        assert include(c,MID).status_code==200
        oldrev=c.get(API).json()['revision']
        assert c.post(API+'/'+MID+'/lifecycle',json={'archived':True,'expectedRevision':oldrev},headers=csrf(c)).status_code==200
        state=c.get(API).json()
        assert MID not in state['standardModuleIds']
        assert include(c,MID,False).status_code==200  # may clear archived global flag
        assert include(c,MID,True).status_code==400
        oldrev=c.get(API).json()['revision']
        assert c.post(API+'/'+MID+'/lifecycle',json={'archived':False,'expectedRevision':oldrev},headers=csrf(c)).status_code==200
        assert MID not in c.get(API).json()['standardModuleIds']


def test_change_audit_is_actor_correct_and_file_is_private(isolated):
    with admin() as c:
        assert include(c,'appointment_reminders').status_code==200
        entries=c.get(API+'/audit').json()['entries']
        assert entries[0]['actor']=='user'
        assert entries[0]['action']=='standard_plan_module_included'
    path=isolated/'global.json'
    assert os.stat(path).st_mode&0o777==0o600
    assert 'passwordHash' not in path.read_text()
    assert 'firebaseCredentials' not in path.read_text()


def test_clinic_specific_api_returns_same_plan_from_verified_session(isolated):
    with admin() as c:
        assert include(c,'appointment_reminders').status_code==200
    for clinic in ('shanlin','yidian'):
        with TestClient(app) as c:
            token=backend.new_session(clinic,role='clinic_admin',username=clinic+'_admin')
            c.cookies.set(backend.COOKIE,token,path='/api/pilot')
            res=c.get('/api/pilot/admin/platform-features')
            assert res.status_code==200,res.text
            assert res.json()['clinicId']==clinic
            assert res.json()['standardPlanFeatures']==['appointment_reminders']
            assert res.json()['availableFeatures']==[]


def test_remote_platform_admin_cannot_open_global_center(isolated):
    class Remote:
        def __init__(self,app):self.app=app
        async def __call__(self,scope,receive,send):
            if scope['type']=='http':scope={**scope,'client':('203.0.113.11',1543)}
            await self.app(scope,receive,send)
    with TestClient(Remote(app)) as c:
        token=backend.new_session(None,role='platform_admin',username='user')
        c.cookies.set(backend.COOKIE,token,path='/api/pilot')
        assert c.get('/platform/modules').status_code==403
        assert c.get(API).status_code==403


def test_original_v32_registry_not_mutated_by_global_plan_toggle(isolated):
    with admin() as c:
        assert add(c).status_code==200
        before=(isolated/'v32.json').read_bytes()
        assert include(c,MID).status_code==200
        assert (isolated/'v32.json').read_bytes()==before


def test_global_plan_cannot_be_set_for_unknown_module(isolated):
    with admin() as c:
        assert include(c,'unknown_module').status_code==404
        assert c.get(API).json()['standardModuleIds']==[]
