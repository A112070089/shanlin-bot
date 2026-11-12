"""v3.6.3 security and original Shanlin backend-schema integration tests. No network/PHI."""
from __future__ import annotations

import importlib
import importlib.util
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import sys
import time
import types

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
for folder in ('website','shanlin_v363_staging','scripts'):
    if str(ROOT/folder) not in sys.path:
        sys.path.insert(0,str(ROOT/folder))
import shanlin_v363_readonly as source
import platform_shanlin_booking_source_v363 as consumer
import install_platform_v363 as installer

SECRET = 'v363-offline-only-authentication-secret-length-above-40-test'
HOST = 'doubts-shanlin-test-default-rtdb.firebaseio.com'


def fake_nodes():
    return {
        'booking_config/clinic':{'clinicId':'shanlin','name':'山林診所', 'integrationV363TestOnly':True},
        'appointments': {
            'A01':{'name':'DO NOT REVEAL NAME', 'idNumber':'TEST-ID-ONE',
                   'phone':'0900-000-001', 'lineUserId':'TEST-LINE-ONE', 'doubtsSyntheticV363':True,
                   'plan':'A','date':'2026-11-03','time':'09:00','note':'private note'},
            'B02':{'name':'PRIVATE SECOND', 'plan':'B','date':'2026-11-03','time':'09:00',
                   'idNumber':'TEST-ID-TWO','phone':'0900-000-002','doubtsSyntheticV363':True},
            'C03':{'name':'PRIVATE THIRD','plan':'C','doubtsSyntheticV363':True,'date':'2026-11-04','time':'10:00'},
        },
        'self_pay_booking': {
            'PKEY2':{'name':'DONT COPY THIS', 'idNumber':'TEST-ID-TWO', 'doubtsSyntheticV363':True,
                     'selfPayItems':[{'name':'private item'}],
                     'selfPayDate':'2026-11-06','selfPayTime':'09:00'},
            'PKEY3':{'name':'HIDDEN SELF PAY', 'phone':'0900-000-099', 'doubtsSyntheticV363':True,
                     'selfPayDate':'2026-11-05','selfPayTime':'14:30',
                     'selfPayTotal':1000},
        },
    }


class FakeRef:
    def __init__(self, values, path):
        self.values=values;self.path=path
    def get(self):
        return self.values.get(self.path)
    def update(self, *a, **kw):
        raise AssertionError('Firebase write attempted')
    def set(self, *a, **kw):
        raise AssertionError('Firebase write attempted')
    def delete(self, *a, **kw):
        raise AssertionError('Firebase delete attempted')


class FakeDb:
    def __init__(self, values=None):
        self.values = values or fake_nodes()
        self.calls=[]
    def reference(self, name):
        self.calls.append(name)
        if name not in {'booking_config/clinic','appointments','self_pay_booking'}:
            raise AssertionError('unexpected database path')
        return FakeRef(self.values,name)


def sign(*, secret=SECRET, stamp=None, nonce=None, path=source.ROUTE):
    stamp=str(int(time.time())) if stamp is None else stamp
    nonce=secrets.token_urlsafe(30) if nonce is None else nonce
    return {'X-DOUBTS-Timestamp':stamp, 'X-DOUBTS-Nonce':nonce,
            'X-DOUBTS-Signature':hmac.new(secret.encode(), f'GET\n{path}\n{stamp}\n{nonce}'.encode('ascii'), hashlib.sha256).hexdigest() }


@pytest.fixture
def setup_env(monkeypatch):
    monkeypatch.setenv('SHANLIN_V363_STAGING_ENABLED','1')
    monkeypatch.setenv('SHANLIN_V363_READ_ENABLED','1')
    monkeypatch.setenv('SHANLIN_V363_SERVICE_SECRET',SECRET)
    monkeypatch.setenv('SHANLIN_V363_TEST_FIREBASE_HOST',HOST)
    monkeypatch.setenv('FIREBASE_URL',f'https://{HOST}/')
    monkeypatch.delenv('FIREBASE_CREDENTIALS',raising=False)
    source._seen.clear()
    yield
    source._seen.clear()


@pytest.fixture
def source_client(setup_env):
    db=FakeDb()
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
    @app.post('/api/admin/appointments')
    def inherited_legacy_write(): return {'FAIL':'should be blocked'}
    source.attach_staging_router(app,db)
    with TestClient(app) as c:
        yield c,db


def test_test_firebase_must_be_explicit(monkeypatch):
    monkeypatch.delenv('SHANLIN_V363_STAGING_ENABLED',raising=False)
    with pytest.raises(RuntimeError): source.check_staging_configuration()


def test_production_firebase_is_rejected(setup_env,monkeypatch):
    monkeypatch.setenv('FIREBASE_URL','https://shanlin-clinic-default-rtdb.firebaseio.com')
    monkeypatch.setenv('SHANLIN_V363_TEST_FIREBASE_HOST','shanlin-clinic-default-rtdb.firebaseio.com')
    with pytest.raises(RuntimeError): source.check_staging_configuration()


def test_unmatched_firebase_host_rejected(setup_env,monkeypatch):
    monkeypatch.setenv('FIREBASE_URL','https://some-other-test-default-rtdb.firebaseio.com')
    with pytest.raises(RuntimeError): source.check_staging_configuration()


@pytest.mark.parametrize('url',[ 'http://'+HOST, 'https://'+HOST+'/appointments',
    'https://evil.example.com','https://'+HOST+'?a=b'])
def test_malformed_firebase_urls_rejected(setup_env,monkeypatch,url):
    monkeypatch.setenv('FIREBASE_URL',url)
    with pytest.raises(RuntimeError): source.check_staging_configuration()


def test_wrong_test_project_credentials_rejected(setup_env,monkeypatch):
    monkeypatch.setenv('FIREBASE_CREDENTIALS',json.dumps({'type':'service_account','project_id':'production-medical'}))
    monkeypatch.setenv('SHANLIN_V363_TEST_PROJECT_ID','doubts-shanlin-test')
    with pytest.raises(RuntimeError):source.check_staging_configuration()


def test_read_disabled_is_423(source_client,monkeypatch):
    c,db=source_client
    monkeypatch.setenv('SHANLIN_V363_READ_ENABLED','0')
    assert c.get(source.ROUTE,headers=sign()).status_code==423
    assert db.calls==[]


def test_read_not_authenticated(source_client):
    c,db=source_client
    assert c.get(source.ROUTE).status_code==401
    assert db.calls==[]


def test_bad_signing_key_rejected(source_client):
    c,db=source_client
    assert c.get(source.ROUTE,headers=sign(secret='another-test-authentication-secret-with-enough-characters')).status_code==401
    assert db.calls==[]


def test_wrong_signing_path_rejected(source_client):
    c,db=source_client
    assert c.get(source.ROUTE,headers=sign(path='/api/admin/appointments')).status_code==401
    assert db.calls==[]


def test_replay_rejected(source_client):
    c,db=source_client
    headers=sign()
    assert c.get(source.ROUTE,headers=headers).status_code==200
    assert c.get(source.ROUTE,headers=headers).status_code==409


@pytest.mark.parametrize('offset',[-75,75])
def test_expired_timestamp_rejected(source_client,offset):
    c,_=source_client
    assert c.get(source.ROUTE,headers=sign(stamp=str(int(time.time())+offset))).status_code==401


def test_existing_backend_mutation_blocked(source_client):
    c,_=source_client
    assert c.post('/api/admin/appointments').status_code==404
    assert c.post(source.ROUTE,headers=sign()).status_code==405
    assert c.get('/admin.html').status_code==404
    assert c.get('/webhook').status_code==404
    assert c.get('/docs').status_code==404


def test_original_shanlin_nodes_are_used_without_patient_data(source_client):
    c,db=source_client
    r=c.get(source.ROUTE,headers=sign())
    assert r.status_code==200
    p=r.json()
    assert db.calls==['booking_config/clinic','appointments','self_pay_booking']
    assert p['count']==4
    assert p['byKind']==[{'kind':'checkup','count':3},{'kind':'self_pay_only','count':1}]
    assert p['slotCounts'][0]['bookedCount']==2
    for name in ('DO NOT REVEAL','TEST-ID','0900-000','DONT COPY','PRIVATE','lineUserId','idNumber','selfPayTotal','PKEY2','PKEY3'):
        assert name not in r.text
    assert r.headers['cache-control'].startswith('no-store')
    assert p['capacityVerified'] is False


def test_original_schema_deduplicates_one_selfpay_booking(setup_env):
    p=source.summarize_original_nodes(fake_nodes()['appointments'],fake_nodes()['self_pay_booking'])
    assert p['byPlan']==[{'plan':'A','count':1},{'plan':'B','count':1},{'plan':'C','count':1},{'plan':'SELF_PAY','count':1}]


def test_wrong_tenant_data_rejected(source_client):
    c,db=source_client
    db.values['appointments']['A01']['clinicId']='yidian'
    assert c.get(source.ROUTE,headers=sign()).status_code==409


def test_unmarked_test_record_refused(source_client):
    c,db=source_client
    del db.values['appointments']['A01']['doubtsSyntheticV363']
    assert c.get(source.ROUTE,headers=sign()).status_code==409


def test_clinic_provenance_required(source_client):
    c,db=source_client
    del db.values['booking_config/clinic']['integrationV363TestOnly']
    assert c.get(source.ROUTE,headers=sign()).status_code==409
    assert db.calls==['booking_config/clinic']


def test_database_read_failure_not_recast_as_empty(source_client):
    c,db=source_client
    class FailDb:
        def reference(self,*a):raise RuntimeError('DB unavailable')
    app=FastAPI();source.attach_staging_router(app,FailDb())
    with TestClient(app) as fail:
        assert fail.get(source.ROUTE,headers=sign()).status_code==503


def test_no_inferred_capacity(setup_env):
    s=source.summarize_original_nodes(fake_nodes()['appointments'],fake_nodes()['self_pay_booking'])
    assert all(x['capacity'] is None and x['availabilityConfirmed'] is False for x in s['slotCounts'])


def test_unknown_dates_never_become_slot_counts(setup_env):
    data=fake_nodes()
    data['appointments']['A01']['date']='2026-22-44'
    value=source.summarize_original_nodes(data['appointments'],data['self_pay_booking'])
    assert len(value['slotCounts'])==3


def test_consumer_rejects_extra_private_fields(setup_env):
    d=source.summarize_original_nodes(fake_nodes()['appointments'],fake_nodes()['self_pay_booking'])
    d['name']='private'
    with pytest.raises(HTTPException): consumer.validate(d)


@pytest.mark.parametrize('change',[{'clinicId':'yidian'},{'isSynthetic':False},
    {'mode':'live'},{'capacityVerified':True},{'containsPatientIdentity':True},
    {'bookingWritesEnabled':True},{'remindersEnabled':True},{'sourceTag':'unknown'}])
def test_consumer_rejects_wrong_contract(setup_env,change):
    d=source.summarize_original_nodes(fake_nodes()['appointments'],fake_nodes()['self_pay_booking'])
    d.update(change)
    with pytest.raises(HTTPException):consumer.validate(d)


def test_consumer_accepts_minimal_aggregate(setup_env):
    d=source.summarize_original_nodes(fake_nodes()['appointments'],fake_nodes()['self_pay_booking'])
    assert consumer.validate(d)==d


def test_consumer_disabled_by_default(monkeypatch):
    monkeypatch.delenv('PILOT_V363_TEST_READ_ENABLED',raising=False)
    with pytest.raises(HTTPException) as e:consumer.read_test_backend_summary()
    assert e.value.status_code==423


def test_fixed_loopback_address():
    assert consumer.ENDPOINT=='http://127.0.0.1:8018/api/integration/v363/booking-summary'
    assert consumer.contract()['productionReadEnabled'] is False


@pytest.fixture
def gateway(monkeypatch):
    mock=types.ModuleType('platform_console')
    mock.NO_CACHE={'Cache-Control':'no-store'}
    def local_only(request:Request):
        if request.client.host not in {'127.0.0.1','testclient'}:
            raise HTTPException(403)
    def platform_read(request:Request):
        if request.headers.get('x-test-role')!='engineer':raise HTTPException(401)
        return {'role':'platform_admin'}
    mock.local_only=local_only;mock.platform_read=platform_read
    monkeypatch.setitem(sys.modules,'platform_console',mock)
    backend=types.ModuleType('pilot_backend')
    def require_clinic(request:Request):
        role=request.headers.get('x-test-role')
        if role is None or role=='engineer':raise HTTPException(401)
        return {'role':'clinic_admin','clinic':'shanlin' if role in ('shanlin','unverified') else 'yidian',
                'legacyConfig':{'name':'山林診所'} if role=='shanlin' else None}
    backend.require_clinic=require_clinic
    monkeypatch.setitem(sys.modules,'pilot_backend',backend)
    sys.modules.pop('platform_shanlin_booking_routes_v363',None)
    routes=importlib.import_module('platform_shanlin_booking_routes_v363')
    monkeypatch.setattr(routes,'read_test_backend_summary',lambda:{'clinicId':'shanlin','count':4})
    app=FastAPI();app.include_router(routes.router)
    with TestClient(app) as c:
        yield c
    sys.modules.pop('platform_shanlin_booking_routes_v363',None)


def test_platform_legacy_permissions(gateway):
    path='/api/pilot/admin/shanlin/booking/v363/test-summary'
    assert gateway.get(path).status_code==401
    assert gateway.get(path,headers={'x-test-role':'yidian'}).status_code==403
    assert gateway.get(path,headers={'x-test-role':'unverified'}).status_code==409
    assert gateway.get(path,headers={'x-test-role':'shanlin'}).status_code==200


def test_engineer_platform_permissions(gateway):
    path='/api/pilot/platform/booking/v363/test-summary'
    assert gateway.get(path).status_code==401
    assert gateway.get(path,headers={'x-test-role':'shanlin'}).status_code==401
    assert gateway.get(path,headers={'x-test-role':'engineer'}).status_code==200


def test_platform_routes_readonly(gateway):
    assert gateway.post('/api/pilot/platform/booking/v363/test-summary',headers={'x-test-role':'engineer'}).status_code==405


def test_pinned_staging_source_has_bootstrap_guard():
    # Runs after add-only installation in the actual Mac project.
    staged=ROOT/'shanlin_v363_staging'/'main.py'
    if not staged.exists():
        pytest.skip('pinned staged source is created during add-only installation')
    text=staged.read_text(encoding='utf-8')
    assert text.startswith(installer.BOOTSTRAP)
    assert text.endswith(installer.HOOK)
    assert 'integrated_app_platform_v363' not in text


def test_add_only_installer_rejects_wrong_source(tmp_path):
    root=tmp_path/'root';root.mkdir()
    src=tmp_path/'shanlin';src.mkdir()
    (src/'main.py').write_text('app=1',encoding='utf-8')
    payloads,errors,actions=installer.inspect(root,src)
    assert errors and any('reviewed v3.5.2' in err for err in errors)


def test_installer_does_not_replace_changed_target(tmp_path,monkeypatch):
    root=tmp_path/'root';root.mkdir()
    src=tmp_path/'shanlin';src.mkdir()
    target=root/'website'/'integrated_app_platform_v363.py'
    target.parent.mkdir(parents=True);target.write_text('untouchable',encoding='utf-8')
    monkeypatch.setattr(installer,'_payloads',lambda *args:({
        'website/integrated_app_platform_v363.py':b'new'
    },[]))
    _,errors,_=installer.inspect(root,src)
    assert any('Refuses to overwrite' in err for err in errors)
    assert target.read_text()=='untouchable'


def test_actual_original_shanlin_main_is_mounted_not_mock_app(setup_env,monkeypatch):
    """Load the pinned ORIGINAL main.py with fake firebase_admin only at the I/O boundary."""
    staged=ROOT/'shanlin_v363_staging'/'main.py'
    if not staged.exists():
        pytest.skip('integration test runs after staged copy installation')
    db=FakeDb()
    fb=types.ModuleType('firebase_admin')
    fb._apps=[]
    fb.initialize_app=lambda *a,**kw: (_ for _ in ()).throw(AssertionError('unapproved firebase init'))
    creds=types.ModuleType('firebase_admin.credentials')
    creds.Certificate=lambda *a,**kw: (_ for _ in ()).throw(AssertionError('unapproved credentials'))
    fb_db=types.ModuleType('firebase_admin.db')
    fb_db.reference=db.reference
    fb.credentials=creds; fb.db=fb_db
    monkeypatch.setitem(sys.modules,'firebase_admin',fb)
    monkeypatch.setitem(sys.modules,'firebase_admin.credentials',creds)
    monkeypatch.setitem(sys.modules,'firebase_admin.db',fb_db)
    monkeypatch.syspath_prepend(str(staged.parent))
    spec=importlib.util.spec_from_file_location('shanlin_v363_original_main_stage_test',staged)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with TestClient(module.app) as c:
        assert c.get('/admin.html').status_code==404
        assert c.post('/api/admin/appointments',json={'name':'FAKE','phone':'000'}).status_code==404
        assert c.post('/webhook').status_code==404
        r=c.get(source.ROUTE,headers=sign())
        assert r.status_code==200 and r.json()['count']==4
        assert db.calls==['booking_config/clinic','appointments','self_pay_booking']
        assert 'DO NOT REVEAL' not in r.text
