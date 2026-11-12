"""Offline verification: v3.6 is local, read-only, auth-scoped and conservative."""
import importlib
import os
from pathlib import Path
import shutil
import sys
import types

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

PATCH = Path(__file__).resolve().parents[1]
WEB = PATCH / 'website'
SCRIPTS = PATCH / 'scripts'
sys.path.insert(0, str(WEB))
sys.path.insert(0, str(SCRIPTS))
import platform_ops_evidence_v36 as ev
from platform_phase36_preflight import check as preflight


def test_reports_never_claim_production():
    result=ev.all_reports(shanlin_catalog_available=True, shanlin_catalog_count=56, module_count=8)
    assert result['productionReady'] is False
    assert result['patientsIncluded'] is False
    assert all(c['bookingWritesEnabled'] is False for c in result['clinics'])
    assert all(c['readiness']=='not_ready_for_live_booking' for c in result['clinics'])


def test_all_checks_have_known_states():
    for c in ev.all_reports(shanlin_catalog_available=False,shanlin_catalog_count=0,module_count=0)['clinics']:
        assert len(c['checks'])==8
        assert all(x['status'] in ('verified_local','pending','blocked') for x in c['checks'])
        assert [x['id'] for x in c['checks']] == ['session','source','catalog','staff','bookings','capacity','modules','release']

@pytest.mark.parametrize('cid',['__proto__','unknown','yidianx','shanlin/../yidian',''])
def test_unknown_tenant_rejected(cid):
    with pytest.raises(ValueError):ev.clinic_report(cid)


def test_shanlin_verified_login_does_not_activate_booking():
    c=ev.clinic_report('shanlin',authenticated=True,shanlin_source_verified=True,
                       shanlin_catalog_available=True,shanlin_catalog_count=56)
    assert c['checks'][0]['status']=='verified_local'
    assert c['checks'][1]['status']=='verified_local'
    assert c['checks'][2]['status']=='verified_local'
    assert next(x for x in c['checks'] if x['id']=='bookings')['status']=='blocked'
    assert next(x for x in c['checks'] if x['id']=='release')['status']=='blocked'


def test_catalog_flag_never_turns_yidian_into_real_clinic():
    c=ev.clinic_report('yidian',authenticated=True,shanlin_source_verified=True,
                       shanlin_catalog_available=True,shanlin_catalog_count=56)
    assert c['role']=='demo'
    assert c['checks'][1]['status']=='pending'
    assert c['checks'][2]['status']=='pending'
    assert '56' not in c['checks'][2]['detail']
    assert c['bookingWritesEnabled'] is False


def test_unsourced_shanlin_never_claims_verified():
    c=ev.clinic_report('shanlin',authenticated=False,shanlin_source_verified=False,
                       shanlin_catalog_available=False)
    assert all(x['status']!='verified_local' for x in c['checks'])


def test_no_patient_records_in_ops_report():
    c=ev.clinic_report('shanlin',authenticated=True,shanlin_source_verified=True,
                       shanlin_catalog_available=True,shanlin_catalog_count=56)
    obj=str(c).lower()
    assert all(key not in obj for key in ('patientid','phone','birthdate','idnumber','password','lineuserid','token'))


def test_preflight_detects_missing_files(tmp_path):
    assert preflight(tmp_path)


def test_preflight_detects_changed_dashboard_anchor(tmp_path):
    for name in ('integrated_app_platform_v35.py','platform_console.py','pilot_backend.py',
                 'platform_standard_policy_v321.py','integrated_app_clinics.py','pilot_shanlin_catalog.py'):
        target=tmp_path/'website'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text('')
    page=tmp_path/'website/platform_static/admin-v321.html';page.parent.mkdir(parents=True,exist_ok=True);page.write_text('<html></html>')
    assert any('工程師首頁版本' in x for x in preflight(tmp_path))


def test_packaged_assets_no_external_script_or_inline_event():
    js=(WEB/'platform_static/clinic-operations-v36.js').read_text()
    html=(WEB/'platform_static/clinic-operations-v36.html').read_text()
    assert 'innerHTML' not in js and 'eval(' not in js
    assert 'http://' not in html and 'https://' not in html
    assert 'onclick=' not in html and '<script>' not in html


@pytest.fixture
def env(monkeypatch,tmp_path):
    """Import router with controlled dependency stubs; never imports live Firebase app."""
    page=tmp_path/'admin-v321.html'
    page.write_text('<html><nav><a href="/platform/modules">功能模組管理中心 →</a></nav></html>',encoding='utf-8')
    shutil.copy2(WEB/'platform_static/clinic-operations-v36.html',tmp_path/'clinic-operations-v36.html')
    shutil.copy2(WEB/'platform_static/clinic-operations-v36.js',tmp_path/'clinic-operations-v36.js')
    platform=types.ModuleType('platform_console')
    platform.STATIC=tmp_path
    platform.NO_CACHE={'Cache-Control':'no-store'}
    def local_only(request: Request):
        if request.client.host not in ('testclient','127.0.0.1'):
            raise HTTPException(403,'local only')
    def platform_read(request: Request):
        if request.headers.get('x-test-role') != 'platform':raise HTTPException(401,'login first')
        local_only(request)
        return {'username':'engineer'}
    platform.local_only=local_only
    platform.platform_read=platform_read
    monkeypatch.setitem(sys.modules,'platform_console',platform)
    backend=types.ModuleType('pilot_backend')
    def require_clinic(request: Request):
        clinic=request.headers.get('x-test-role')
        if clinic not in ('yidian','shanlin','other'):
            raise HTTPException(401,'clinic login required')
        return {'clinic':clinic,'legacyConfig':{'clinic':'shanlin'} if clinic=='shanlin' else None}
    backend.require_clinic=require_clinic
    monkeypatch.setitem(sys.modules,'pilot_backend',backend)
    cat=types.ModuleType('pilot_shanlin_catalog')
    cat.snapshot_source_catalog=lambda _: {'available':True,'count':56}
    monkeypatch.setitem(sys.modules,'pilot_shanlin_catalog',cat)
    policy=types.ModuleType('platform_standard_policy_v321')
    policy.read_state=lambda : {'modules':[{'id':'voice'},{'id':'catalog'}]}
    monkeypatch.setitem(sys.modules,'platform_standard_policy_v321',policy)
    sys.modules.pop('platform_ops_routes_v36',None)
    routes=importlib.import_module('platform_ops_routes_v36')
    app=FastAPI();app.include_router(routes.router)
    with TestClient(app) as client:
        yield client, page, routes
    sys.modules.pop('platform_ops_routes_v36',None)


def test_engineer_view_denies_unauthenticated(env):
    client,_,_=env
    r=client.get('/api/pilot/platform/operations/v36/summary')
    assert r.status_code==401


def test_engineer_view_scopes_safe_summary(env):
    client,_,_=env
    r=client.get('/api/pilot/platform/operations/v36/summary',headers={'x-test-role':'platform'})
    assert r.status_code==200 and r.headers['cache-control']=='no-store'
    data=r.json()
    assert data['productionReady'] is False
    assert set(x['clinicId'] for x in data['clinics'])=={'yidian','shanlin'}
    assert data['clinics'][1]['checks'][1]['status']=='pending'  # No engineer-source attestation


def test_clinic_view_denies_unauthenticated(env):
    client,_,_=env
    assert client.get('/api/pilot/admin/operations/v36/summary').status_code==401

@pytest.mark.parametrize('target',['yidian','shanlin'])
def test_clinic_view_bound_to_authenticated_session_not_query(env,target):
    client,_,_=env
    spoof='shanlin' if target=='yidian' else 'yidian'
    r=client.get('/api/pilot/admin/operations/v36/summary?clinic='+spoof,
                 headers={'x-test-role':target})
    assert r.status_code==200 and r.json()['clinicId']==target
    assert r.json()['bookingWritesEnabled'] is False


def test_clinic_view_rejects_unknown_session_tenant(env):
    client,_,_=env
    assert client.get('/api/pilot/admin/operations/v36/summary',
                      headers={'x-test-role':'other'}).status_code==403


def test_html_uses_original_dashboard_without_overwrite(env):
    client,page,_=env
    before=page.read_bytes()
    r=client.get('/platform/admin')
    assert r.status_code==200
    assert '診所營運整合驗收' in r.text
    assert '功能模組管理中心' in r.text
    assert r.headers['cache-control']=='no-store'
    assert page.read_bytes()==before


def test_html_change_fails_closed(env):
    client,page,_=env
    page.write_text('<html>new version</html>',encoding='utf-8')
    assert client.get('/platform/admin').status_code==503


def test_no_mutation_routes(env):
    client,page,routes=env
    assert all('GET' in route.methods for route in routes.router.routes)
    assert client.post('/api/pilot/platform/operations/v36/summary').status_code==405
    assert client.post('/api/pilot/admin/operations/v36/summary').status_code==405


def test_safe_headers_and_local_assets(env):
    client,page,_=env
    r=client.get('/platform/operations')
    assert r.status_code==200
    assert "frame-ancestors 'none'" in r.headers['content-security-policy']
    assert client.get('/platform/assets/clinic-operations-v36.js').status_code==200


def test_inherited_app_clone_preserves_source(monkeypatch,env):
    source=FastAPI()
    @source.get('/health-source')
    def ok():return {'ok':True}
    obj=types.ModuleType('integrated_app_platform_v35')
    obj.app=source
    monkeypatch.setitem(sys.modules,'integrated_app_platform_v35',obj)
    sys.modules.pop('integrated_app_platform_v36',None)
    candidate=importlib.import_module('integrated_app_platform_v36').app
    assert candidate is not source
    assert any(x.path=='/health-source' for x in candidate.routes)
    assert not any(x.path=='/platform/operations' for x in source.routes)
    assert any(x.path=='/platform/operations' for x in candidate.routes)
    sys.modules.pop('integrated_app_platform_v36',None)


def test_safe_installer_only_contains_new_v36_files():
    from install_platform_v36 import RELATIVE
    assert len(RELATIVE)==8
    assert all(('_v36' in x or '-v36' in x or 'phase36' in x) for x in RELATIVE)
    assert not any('main.py' in x or 'index.html' in x or 'appointment' in x for x in RELATIVE)


def test_install_fails_closed_on_existing_diff(tmp_path):
    from install_platform_v36 import inspect, RELATIVE
    target=tmp_path/RELATIVE[0];target.parent.mkdir(parents=True);target.write_text('manually changed')
    problems,_=inspect(tmp_path)
    assert problems and any('不允許覆寫' in msg for msg in problems)


def test_install_is_idempotent_in_clean_fixture(tmp_path):
    from install_platform_v36 import install, RELATIVE
    import platform_phase36_preflight as pre
    for f in pre.REQUIRED:
        path=tmp_path/f;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('<a href="/platform/modules">功能模組管理中心 →</a>' if path.suffix=='.html' else '# required original')
    issues,_=install(tmp_path)
    assert not issues
    assert all((tmp_path/f).is_file() for f in RELATIVE)
    issues,_=install(tmp_path)
    assert not issues
