"""DOUBTS v3.3 release-tracking workflow: human report != trusted deployment."""
from pathlib import Path
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'website'))
from integrated_app_platform_v33 import app
import pilot_backend as backend
import platform_console_store as v1
import platform_module_store_v32 as modules
import platform_standard_policy_v321 as standard
import platform_clinic_registry as clinics
import platform_onboarding_store_v3 as onboarding
import platform_release_store_v33 as release

MOD_API='/api/pilot/platform/console/modules'
API='/api/pilot/platform/console/releases'
MID='ai_health_summary'
SHA='abc1234def56'

@pytest.fixture
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(release,'_paths',lambda:(tmp_path/'releases.json',tmp_path/'release.lock'))
    monkeypatch.setattr(standard,'_paths',lambda:(tmp_path/'global.json',tmp_path/'global.lock'))
    monkeypatch.setattr(modules,'_paths',lambda:(tmp_path/'modules.json',tmp_path/'modules.lock'))
    monkeypatch.setattr(v1,'_paths',lambda:(tmp_path/'v1.json',tmp_path/'v1.lock'))
    monkeypatch.setattr(clinics,'_paths',lambda:(tmp_path/'clinics.json',tmp_path/'clinics.lock'))
    monkeypatch.setattr(onboarding,'_paths',lambda:(tmp_path/'onboarding.json',tmp_path/'onboarding.lock'))
    monkeypatch.setattr(backend,'accounts_path',lambda:tmp_path/'accounts.json')
    monkeypatch.setattr(standard,'VERIFIED_LIVE_CLINICS',frozenset())
    modules.VERIFIED_RUNTIME_ADAPTERS.clear()
    backend._sessions.clear(); backend._failed.clear()
    yield tmp_path
    modules.VERIFIED_RUNTIME_ADAPTERS.clear()


def engineer():
    client=TestClient(app)
    token=backend.new_session(None,role='platform_admin',username='user')
    client.cookies.set(backend.COOKIE,token,path='/api/pilot')
    return client


def csrf(c):
    return {'Origin':'http://testserver','X-Pilot-CSRF':c.get('/api/pilot/platform/console/session').json()['csrf']}


def write(c,operation,payload=None,mid=MID,expected=None):
    if expected is None: expected=c.get(API+'/'+mid).json()['revision']
    return c.post(API+'/'+mid+operation,json={**(payload or {}),'expectedRevision':expected},headers=csrf(c))


def start_test(c,mid=MID,ref=SHA):
    assert write(c,'/progress',{'progress':'testing','codeReference':ref},mid=mid).status_code==200


def set_checks(c,mid=MID):
    for key in release.CHECKS:
        result=write(c,'/checks/'+key,{'status':'passed','evidence':'pytest report: 195 passed'},mid=mid)
        assert result.status_code==200,result.text


def include(c,mid=MID):
    current=c.get(MOD_API).json()['policyRevision']
    result=c.post(MOD_API+'/'+mid+'/standard',json={'enabled':True,'expectedPolicyRevision':current},headers=csrf(c))
    assert result.status_code==200,result.text


def submit(c,mid=MID):
    return write(c,'/submit',mid=mid)


def test_v33_200_pages_and_no_clinic_checkbox(isolated):
    with TestClient(app) as c:
        page=c.get('/platform/modules')
        assert page.status_code==200
        assert 'module-center-v33.js' in page.text
        assert c.get('/platform/modules/'+MID+'/release').status_code==200
        assert 'module-release-v33.js' in c.get('/platform/modules/'+MID+'/release').text
        assert c.get('/platform/modules/not-real/release').status_code==404
        for name in ['module-center-v33.js','module-center-v33.css','module-release-v33.js','module-release-v33.css']:
            assert c.get('/platform/assets/'+name).status_code==200
        js=c.get('/platform/assets/module-center-v33.js').text
        assert '部署／驗收' in js and 'data-clinic=' not in js
        assert 'module-release-link' in c.get('/platform/assets/module-center-v33.css').text
        assert "script-src 'self'" in page.headers['Content-Security-Policy']


def test_read_does_not_create_file_or_promote_grants(isolated):
    with engineer() as c:
        data=c.get(API+'/'+MID).json()
        assert data['revision']==release.ZERO
        assert data['release']['progress']=='planned'
        assert not data['release']['deploymentVerified']
        assert not data['release']['standardIncluded']
        assert c.get(API).json()['releases'][0]['deploymentVerified'] is False
    assert not (isolated/'releases.json').exists()
    assert not (isolated/'modules.json').exists()
    assert not (isolated/'global.json').exists()


def test_progress_is_persisted_with_actor_audit_and_mode_0600(isolated):
    with engineer() as c:
        res=write(c,'/progress',{'progress':'developing','codeReference':''})
        assert res.status_code==200,res.text
        assert res.json()['release']['progress']=='developing'
        assert c.get(API+'/'+MID).json()['release']['progress']=='developing'
        log=c.get(API+'/'+MID+'/audit').json()['entries']
        assert log[0]['action']=='release_progress_updated'
        assert log[0]['actor']=='user'
    assert os.stat(isolated/'releases.json').st_mode & 0o777 == 0o600
    assert json.loads((isolated/'releases.json').read_text())['schemaVersion']==330


def test_wrong_code_reference_is_rejected(isolated):
    with engineer() as c:
        assert write(c,'/progress',{'progress':'testing','codeReference':'secret-groqqq'}).status_code==422
        assert write(c,'/progress',{'progress':'testing','codeReference':'123456'}).status_code==422
        assert write(c,'/progress',{'progress':'deployed','codeReference':''}).status_code==422
        assert c.get(API+'/'+MID).json()['release']['progress']=='planned'


def test_checks_require_evidence_and_track_report_not_machine_test(isolated):
    with engineer() as c:
        assert write(c,'/checks/unit_tests',{'status':'passed','evidence':'a'}).status_code==400
        assert write(c,'/checks/unit_tests',{'status':'passed','evidence':'pytest report 195 passed'}).status_code==200
        state=c.get(API+'/'+MID).json()['release']
        assert state['checks']['unit_tests']['status']=='passed'
        assert not state['deploymentVerified']
        assert state['acceptance']=='draft'
        assert write(c,'/checks/unit_tests',{'status':'pending','evidence':''}).status_code==200
        assert write(c,'/checks/unknown',{'status':'passed','evidence':'report number 15'}).status_code==400


def test_submit_requires_code_reference_testing_and_all_checks(isolated):
    with engineer() as c:
        include(c)
        assert submit(c).status_code==400
        start_test(c)
        assert submit(c).status_code==400
        set_checks(c)
        res=submit(c)
        assert res.status_code==200,res.text
        state=res.json()['release']
        assert state['acceptance']=='submitted'
        assert not state['canApprove']
        assert not state['acceptedEffective']
        assert not state['deploymentVerified']
        assert c.get(MOD_API).json()['standardModuleIds']==[MID]
        assert standard.clinic_entitlements('shanlin')['availableFeatures']==[]


def test_not_in_standard_plan_cannot_submit(isolated):
    with engineer() as c:
        start_test(c)
        set_checks(c)
        assert submit(c).status_code==400
        assert c.get(API+'/'+MID).json()['release']['acceptance']=='draft'


def test_failed_check_blocks_submit(isolated):
    with engineer() as c:
        include(c);start_test(c);set_checks(c)
        assert write(c,'/checks/authorization',{'status':'failed','evidence':'Access forbidden test failed'}).status_code==200
        assert submit(c).status_code==400


def test_withdraw_allows_editing_again(isolated):
    with engineer() as c:
        include(c);start_test(c);set_checks(c);assert submit(c).status_code==200
        assert write(c,'/progress',{'progress':'planned','codeReference':''}).status_code==400
        assert write(c,'/checks/unit_tests',{'status':'pending','evidence':''}).status_code==400
        assert write(c,'/withdraw').status_code==200
        assert write(c,'/progress',{'progress':'developing','codeReference':''}).status_code==200
        assert c.get(API+'/'+MID).json()['release']['acceptance']=='draft'


def test_rejection_and_resubmission_flow(isolated):
    with engineer() as c:
        include(c);start_test(c);set_checks(c);assert submit(c).status_code==200
        assert write(c,'/reject',{'reason':'需重新檢查跨診所授權'}).status_code==200
        assert c.get(API+'/'+MID).json()['release']['acceptance']=='rejected'
        assert write(c,'/checks/authorization',{'status':'passed','evidence':'New permission test passed'}).status_code==200
        assert c.get(API+'/'+MID).json()['release']['acceptance']=='draft'
        assert submit(c).status_code==200


def test_approval_blocked_without_trusted_runtime_even_if_passed(isolated):
    with engineer() as c:
        include(c);start_test(c);set_checks(c);assert submit(c).status_code==200
        assert write(c,'/approve').status_code==400
        assert c.get(API+'/'+MID).json()['release']['deploymentVerified'] is False


def test_engineer_cannot_write_fake_deployed_status_through_api(isolated):
    with engineer() as c:
        assert c.post(API+'/'+MID+'/progress',json={'progress':'deployed','codeReference':SHA,'expectedRevision':release.ZERO},headers=csrf(c)).status_code==422
        assert c.post(API+'/'+MID+'/approve',json={'expectedRevision':release.ZERO,'verified':True},headers=csrf(c)).status_code==400
        assert not (isolated/'releases.json').exists()


def test_trusted_code_registration_enables_approval_only_after_qa_and_submission(isolated,monkeypatch):
    with engineer() as c:
        include(c)
        monkeypatch.setitem(modules.VERIFIED_RUNTIME_ADAPTERS,MID,
                           {'verified':True,'codeIntegrated':True,'version':'0.1.0'})
        assert write(c,'/approve').status_code==400
        start_test(c);set_checks(c);assert submit(c).status_code==200
        assert write(c,'/approve').status_code==200
        row=c.get(API+'/'+MID).json()['release']
        assert row['acceptedEffective'] is True
        assert row['deploymentVerified'] is True
        assert standard.clinic_entitlements('shanlin')['availableFeatures']==[]
        assert standard.clinic_entitlements('yidian')['availableFeatures']==[]


def test_changing_module_version_starts_fresh_release_record(isolated):
    with engineer() as c:
        include(c);start_test(c);set_checks(c);submit(c)
        state=c.get(MOD_API).json()
        mod=next(x for x in state['modules'] if x['id']==MID)
        changed=c.patch(MOD_API+'/'+MID,json={'name':mod['name'],'description':mod['description'],
              'plannedVersion':'0.2.0','stage':'testing','expectedRevision':state['revision']},headers=csrf(c))
        assert changed.status_code==200,changed.text
        result=c.get(API+'/'+MID).json()
        assert result['release']['version']=='0.2.0'
        assert result['release']['progress']=='planned'
        assert result['release']['acceptance']=='draft'
        assert '0.1.0' in result['historicalVersions']
        data=json.loads((isolated/'releases.json').read_text())
        assert data['releases'][MID]['0.1.0']['acceptance']=='submitted'


def test_archived_module_cannot_write_release_records(isolated):
    with engineer() as c:
        state=c.get(MOD_API).json()
        changed=c.post(MOD_API+'/'+MID+'/lifecycle',json={
            'archived':True,'expectedRevision':state['revision']},headers=csrf(c))
        assert changed.status_code==200
        assert write(c,'/progress',{'progress':'developing','codeReference':''}).status_code==400


def test_revoke_global_plan_invalidates_release_approval(isolated,monkeypatch):
    with engineer() as c:
        include(c);start_test(c);set_checks(c);submit(c)
        monkeypatch.setitem(modules.VERIFIED_RUNTIME_ADAPTERS,MID,
                           {'verified':True,'codeIntegrated':True,'version':'0.1.0'})
        assert write(c,'/approve').status_code==200
        state=c.get(MOD_API).json()
        r=c.post(MOD_API+'/'+MID+'/standard',json={'enabled':False,
                  'expectedPolicyRevision':state['policyRevision']},headers=csrf(c))
        assert r.status_code==200
        rel=c.get(API+'/'+MID).json()['release']
        assert rel['acceptance']=='approved'
        assert rel['acceptedEffective'] is False


def test_two_engineer_windows_conflict_on_revision(isolated):
    with engineer() as a,engineer() as b:
        revision=a.get(API+'/'+MID).json()['revision']
        assert write(b,'/progress',{'progress':'developing','codeReference':''}).status_code==200
        stale=write(a,'/progress',{'progress':'testing','codeReference':SHA},expected=revision)
        assert stale.status_code==409
        assert a.get(API+'/'+MID).json()['release']['progress']=='developing'


def test_clinic_user_and_unauthenticated_cannot_edit(isolated):
    with TestClient(app) as c:
        assert c.get(API+'/'+MID).status_code in (401,403)
        assert c.get(API).status_code in (401,403)
        assert c.post(API+'/'+MID+'/approve',json={'expectedRevision':release.ZERO}).status_code in (401,403)
        token=backend.new_session('shanlin',role='clinic_admin',username='shanlin_admin')
        c.cookies.set(backend.COOKIE,token,path='/api/pilot')
        assert c.get(API+'/'+MID).status_code==403
        assert c.post(API+'/'+MID+'/progress',json={
            'progress':'developing','codeReference':'','expectedRevision':release.ZERO}).status_code==403
    with engineer() as c:
        payload={'progress':'developing','codeReference':'','expectedRevision':release.ZERO}
        assert c.post(API+'/'+MID+'/progress',json=payload).status_code==403
        assert c.post(API+'/'+MID+'/progress',json=payload,headers={
             'Origin':'https://evil.test','X-Pilot-CSRF':csrf(c)['X-Pilot-CSRF']}).status_code==403
    assert not (isolated/'releases.json').exists()


def test_unexpected_host_and_external_client_are_rejected(isolated):
    with TestClient(app,base_url='http://evil.example') as c:
        assert c.get('/platform/modules').status_code==403


def test_invalid_json_fails_closed_without_overwriting(isolated):
    (isolated/'releases.json').write_text('do not overwrite')
    with engineer() as c:
        response=c.get(API+'/'+MID)
        assert response.status_code==503
        response=write(c,'/progress',{'progress':'testing','codeReference':SHA},expected=release.ZERO)
        assert response.status_code==503
    assert (isolated/'releases.json').read_text()=='do not overwrite'


def test_existing_v321_records_untouched(isolated):
    with engineer() as c:
        include(c)
        prev=(isolated/'global.json').read_bytes()
        assert write(c,'/progress',{'progress':'testing','codeReference':SHA}).status_code==200
        assert (isolated/'global.json').read_bytes()==prev
        assert not (isolated/'modules.json').exists()


def test_audit_is_per_module_and_version_bound(isolated):
    with engineer() as c:
        assert write(c,'/progress',{'progress':'developing','codeReference':''}).status_code==200
        assert c.get(API+'/staff_worklist/audit').json()['entries']==[]
        overview=c.get(API).json()
        assert len(overview['releases'])==3
        assert all(not row['acceptedEffective'] for row in overview['releases'])


def test_client_supplied_timestamp_or_deployment_does_not_change_state(isolated):
    with engineer() as c:
        response=c.post(API+'/'+MID+'/progress',json={
            'progress':'testing','codeReference':SHA,'expectedRevision':release.ZERO,
            'deploymentVerified':True,'actor':'intruder','approvedAt':'yesterday'},headers=csrf(c))
        assert response.status_code==200
        data=c.get(API+'/'+MID).json()['release']
        assert data['deploymentVerified'] is False
        assert data['acceptance']=='draft'
        assert c.get(API+'/'+MID+'/audit').json()['entries'][0]['actor']=='user'


def test_v33_clinic_entitlement_requires_accepted_version(isolated,monkeypatch):
    monkeypatch.setitem(modules.VERIFIED_RUNTIME_ADAPTERS,MID,
                       {'verified':True,'codeIntegrated':True,'version':'0.1.0'})
    monkeypatch.setattr(standard,'VERIFIED_LIVE_CLINICS',frozenset({'shanlin'}))
    with engineer() as c:
        include(c)
        assert standard.clinic_entitlements('shanlin')['availableFeatures']==[MID]
        assert release.clinic_entitlements('shanlin')['availableFeatures']==[]
        start_test(c);set_checks(c);submit(c)
        assert release.clinic_entitlements('shanlin')['availableFeatures']==[]
        assert write(c,'/approve').status_code==200
        assert release.clinic_entitlements('shanlin')['availableFeatures']==[MID]
        token=backend.new_session('shanlin',role='clinic_admin',username='shanlin_admin')
        c.cookies.set(backend.COOKIE,token,path='/api/pilot')
        result=c.get('/api/pilot/admin/platform-features')
        assert result.status_code==200,result.text
        assert result.json()['availableFeatures']==[MID]


def test_new_build_requires_fresh_test_evidence(isolated):
    with engineer() as c:
        include(c);start_test(c,ref=SHA);set_checks(c)
        assert c.get(API+'/'+MID).json()['release']['allChecksReportedPassed']
        newer=write(c,'/progress',{'progress':'testing','codeReference':'0123456789abcd'})
        assert newer.status_code==200,newer.text
        row=newer.json()['release']
        assert not row['allChecksReportedPassed']
        assert all(x['status']=='pending' for x in row['checks'].values())
        assert submit(c).status_code==400
        set_checks(c);assert submit(c).status_code==200
