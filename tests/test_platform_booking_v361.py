"""Local, no production network or patient data. Cases test authorization and shape."""
import ast
from pathlib import Path
import importlib
import json
import sys
import types

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

PATCH = Path(__file__).resolve().parents[1]
for d in ('website','scripts','sandbox'):
    loc=str(PATCH/d)
    if loc not in sys.path:sys.path.insert(0,loc)
import platform_shanlin_booking_source_v361 as source
import install_platform_v361 as inst

HASH_KEY=b'test-only-hmac-key-at-least-32-characters-123'


def test_fixed_loopback_url_only():
    assert source.SANDBOX_ORIGIN=='http://127.0.0.1:8017'
    assert set(source._SANDBOX_ENDPOINTS)=={'/api/admin/clinic-config','/api/admin/appointments'}


def test_safe_contract_requires_verified_session():
    result=source.source_contract()
    assert result['productionReadEnabled'] is False
    assert result['bookingWritesEnabled'] is False
    assert 'idNumber' in result['identityFieldsExcluded']


def test_sandbox_disabled_by_default(monkeypatch):
    monkeypatch.delenv('PILOT_V361_SANDBOX_READ_ENABLED', raising=False)
    with pytest.raises(HTTPException) as e:source.read_shanlin_sandbox()
    assert e.value.status_code==423


def test_keys_must_be_distinct_and_long(monkeypatch):
    monkeypatch.setenv('PILOT_V361_SANDBOX_READ_ENABLED','1')
    monkeypatch.setenv('PILOT_V361_SANDBOX_TOKEN','x')
    monkeypatch.setenv('PILOT_V361_SANDBOX_HASH_KEY','x')
    with pytest.raises(HTTPException) as e:source.read_shanlin_sandbox()
    assert e.value.status_code==503


def test_rejects_any_other_endpoint():
    with pytest.raises(HTTPException) as e:source._get_json('/api/admin/users','x'*24)
    assert e.value.status_code==503


def fixture_payload():
    return {'sourceTag':source.SANDBOX_TAG,'appointments':[
        {'_key':'A123456789','idNumber':'A123456789','name':'Sensitive Example',
         'phone':'0912345678','lineUserId':'U_secret','birth':'2000-01-01',
         'note':'patient private note','date':'2026-11-03','time':'09:00','plan':'A',
         'source':'電話','_pureSelfPay':False,'_hasSelfPay':False},
        {'_key':'SELF_PAY_0912345555','name':'secret person','phone':'0912345555',
         'selfPayDate':'2026-11-05','selfPayTime':'14:30','source':'SELF_PAY_BOOKING',
         '_hasSelfPay':True,'_pureSelfPay':True},
    ]}


def test_normalize_removes_all_private_data():
    data=source.normalize_synthetic_bookings(fixture_payload(),hash_key=HASH_KEY)
    rendered=json.dumps(data,ensure_ascii=False)
    for private in ('A123456789','0912345678','0912345555','Sensitive Example',
                    'secret person','U_secret','patient private note','2000-01-01'):
        assert private not in rendered
    assert data['count']==2
    assert data['appointments'][1]['kind']=='self_pay_only'
    assert data['appointments'][1]['plan']=='SELF_PAY'
    assert len(data['appointments'][0]['ref'])==24
    assert data['containsPatientIdentity'] is False
    assert data['capacityVerified'] is False


def test_hmac_reference_is_stable_not_raw():
    a=source.normalize_synthetic_bookings(fixture_payload(),hash_key=HASH_KEY)
    b=source.normalize_synthetic_bookings(fixture_payload(),hash_key=HASH_KEY)
    assert a['appointments'][0]['ref']==b['appointments'][0]['ref']
    c=source.normalize_synthetic_bookings(fixture_payload(),hash_key=b'new-long-testing-key-32-characters')
    assert a['appointments'][0]['ref']!=c['appointments'][0]['ref']


@pytest.mark.parametrize('change',[
    {'sourceTag':'wrong'}, {'sourceTag':None}, {'appointments':{}},
    {'appointments':[None]}, {'appointments':[{'name':'no key'}]},
])
def test_fail_closed_on_bad_source_shape(change):
    payload=fixture_payload()
    payload.update(change)
    with pytest.raises(HTTPException) as e:
        source.normalize_synthetic_bookings(payload,hash_key=HASH_KEY)
    assert e.value.status_code==503


def test_invalid_dates_no_availability_claim():
    payload={'sourceTag':source.SANDBOX_TAG,'appointments':[
        {'_key':'1','date':'2026-02-30','time':'27:00','plan':'<script>',
         'source':'91-234-5678','_hasSelfPay':False},
    ]}
    data=source.normalize_synthetic_bookings(payload,hash_key=HASH_KEY)
    assert data['appointments'][0]['date'] is None
    assert data['appointments'][0]['time'] is None
    assert data['appointments'][0]['plan']=='other'
    assert data['appointments'][0]['source']=='其他'
    assert data['slotCounts']==[]


def test_same_slot_count_not_capacity():
    payload=fixture_payload()
    payload['appointments'].append({'_key':'other','date':'2026-11-03','time':'09:00','plan':'B'})
    result=source.normalize_synthetic_bookings(payload,hash_key=HASH_KEY)
    assert result['slotCounts'][0]['bookedCount']==2
    assert result['slotCounts'][0]['capacity'] is None
    assert result['slotCounts'][0]['availabilityConfirmed'] is False


def test_duplicate_key_fails():
    payload=fixture_payload()
    payload['appointments'].append({'_key':'A123456789'})
    with pytest.raises(HTTPException) as e:
        source.normalize_synthetic_bookings(payload,hash_key=HASH_KEY)
    assert e.value.status_code==503


def test_large_payload_fails():
    payload={'sourceTag':source.SANDBOX_TAG,'appointments':[{}]*1001}
    with pytest.raises(HTTPException) as e:source.normalize_synthetic_bookings(payload,hash_key=HASH_KEY)
    assert e.value.status_code==503


@pytest.fixture
def routing_env(monkeypatch):
    platform=types.ModuleType('platform_console')
    platform.NO_CACHE={'Cache-Control':'no-store'}
    def local_only(request:Request):
        if request.client.host not in ('testclient','127.0.0.1'):
            raise HTTPException(403,'local only')
    def platform_read(request:Request):
        if request.headers.get('x-test-role')!='platform':
            raise HTTPException(401,'engineer login required')
        return {'role':'platform'}
    platform.local_only=local_only
    platform.platform_read=platform_read
    monkeypatch.setitem(sys.modules,'platform_console',platform)
    backend=types.ModuleType('pilot_backend')
    def require_clinic(request:Request):
        role=request.headers.get('x-test-role')
        if role not in ('shanlin','yidian','unverified'):
            raise HTTPException(401,'clinic login required')
        return {'clinic':'yidian' if role=='yidian' else 'shanlin',
                'legacyConfig':{'name':'山林診所'} if role=='shanlin' else None}
    backend.require_clinic=require_clinic
    monkeypatch.setitem(sys.modules,'pilot_backend',backend)
    sys.modules.pop('platform_shanlin_booking_routes_v361',None)
    routes=importlib.import_module('platform_shanlin_booking_routes_v361')
    app=FastAPI()
    app.include_router(routes.router)
    with TestClient(app) as client:
        yield client, routes
    sys.modules.pop('platform_shanlin_booking_routes_v361',None)


def test_engineer_contract_auth(routing_env):
    client,_=routing_env
    assert client.get('/api/pilot/platform/booking/v361/contract').status_code==401
    r=client.get('/api/pilot/platform/booking/v361/contract',headers={'x-test-role':'platform'})
    assert r.status_code==200 and r.json()['bookingWritesEnabled'] is False
    assert r.headers['cache-control']=='no-store'



def test_engineer_sandbox_bridge_requires_engineer(routing_env,monkeypatch):
    client,_=routing_env
    monkeypatch.setattr('platform_shanlin_booking_routes_v361.read_shanlin_sandbox',
                        lambda: {'clinicId':'shanlin','mode':'sandbox_only','isSynthetic':True})
    url='/api/pilot/platform/booking/v361/sandbox-snapshot'
    assert client.get(url).status_code==401
    assert client.get(url,headers={'x-test-role':'shanlin'}).status_code==401
    r=client.get(url,headers={'x-test-role':'platform'})
    assert r.status_code==200
    assert r.json()['mode']=='sandbox_only'
    assert r.headers['cache-control']=='no-store'


def test_clinic_access_policy(routing_env,monkeypatch):
    client,_=routing_env
    monkeypatch.setattr('platform_shanlin_booking_routes_v361.read_shanlin_sandbox',
                        lambda: {'clinicId':'shanlin','mode':'sandbox_only'})
    url='/api/pilot/admin/shanlin/booking/v361/snapshot?clinic=shanlin'
    assert client.get(url).status_code==401
    assert client.get(url,headers={'x-test-role':'yidian'}).status_code==403
    assert client.get(url,headers={'x-test-role':'unverified'}).status_code==409
    r=client.get(url+'?clinic=yidian',headers={'x-test-role':'shanlin'})
    assert r.status_code==200
    assert r.json()['clinicId']=='shanlin'
    assert r.headers['cache-control']=='no-store'


def test_no_write_endpoints(routing_env):
    client,routes=routing_env
    assert all(route.methods == {'GET'} for route in routes.router.routes)
    assert client.post('/api/pilot/admin/shanlin/booking/v361/snapshot').status_code==405
    assert client.post('/api/pilot/platform/booking/v361/sandbox-snapshot').status_code==405


def test_sandbox_token_is_enforced(monkeypatch):
    sandbox=importlib.import_module('shanlin_readonly_sandbox_v361')
    monkeypatch.setenv('PILOT_V361_SANDBOX_TOKEN','local-only-24-character-sandbox-token')
    with TestClient(sandbox.app) as client:
        url='/api/admin/appointments'
        assert client.get(url).status_code==403
        r=client.get(url,headers={'X-Sandbox-Token':'local-only-24-character-sandbox-token'})
        assert r.status_code==200
        assert r.json()['sourceTag']==source.SANDBOX_TAG
        assert len(r.json()['appointments'])==4
        assert client.post(url).status_code==405


def test_app_clone_preserves_v36(monkeypatch):
    original=FastAPI()
    @original.get('/v36-existing')
    def exists():return {'ok':True}
    base=types.ModuleType('integrated_app_platform_v36')
    base.app=original
    monkeypatch.setitem(sys.modules,'integrated_app_platform_v36',base)
    extra=types.ModuleType('platform_shanlin_booking_routes_v361')
    from fastapi import APIRouter
    extra.router=APIRouter()
    @extra.router.get('/new-v361')
    def new():return {'ok':True}
    monkeypatch.setitem(sys.modules,'platform_shanlin_booking_routes_v361',extra)
    sys.modules.pop('integrated_app_platform_v361',None)
    joined=importlib.import_module('integrated_app_platform_v361').app
    assert joined is not original
    assert any(x.path=='/v36-existing' for x in joined.routes)
    assert any(x.path=='/new-v361' for x in joined.routes)
    assert not any(x.path=='/new-v361' for x in original.routes)
    sys.modules.pop('integrated_app_platform_v361',None)


def test_installer_only_adds_files():
    assert len(inst.FILES)==6
    assert not any('main.py' in x or 'index.html' in x or 'appointment2.html' in x for x in inst.FILES)
    assert all('v361' in x for x in inst.FILES)


def test_install_prohibits_conflicts(tmp_path):
    p=tmp_path/inst.FILES[0]
    p.parent.mkdir(parents=True)
    p.write_text('custom patch')
    errors,_=inst.inspect(tmp_path)
    assert any('絕不覆蓋' in x for x in errors)


def test_install_idempotence_in_fake_tree(tmp_path):
    for f in inst.REQUIRED:
        p=tmp_path/f
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text('def ok(): pass' if p.suffix=='.py' else '')
    errors,_=inst.install(tmp_path)
    assert errors==[]
    errors,_=inst.install(tmp_path)
    assert errors==[]
    assert all((tmp_path/f).is_file() for f in inst.FILES)
