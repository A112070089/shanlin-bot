"""v362 integration and security tests. Pure local synthetic fixtures."""
from __future__ import annotations
from copy import deepcopy
import importlib
import json
import os
from pathlib import Path
import secrets
import sys
import time
import types

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
for folder in ('website', 'sandbox', 'scripts'):
    p = str(ROOT / folder)
    if p not in sys.path:
        sys.path.insert(0,p)
import platform_shanlin_booking_source_v362 as consumer
import shanlin_v362_source_router as producer
import install_platform_v362 as installer

SECRET = 'local-test-service-secret-for-v362-not-for-production-123456'


def synthetics():
    return [
        {'_key':'FAKE-001', 'name':'FAKE PERSON', 'phone':'FAKE PHONE',
         'idNumber':'FAKE ID', 'lineUserId':'FAKE LINE', 'note':'FAKE NOTE',
         'date':'2026-11-03', 'time':'09:00', 'plan':'A'},
        {'_key':'FAKE-002', 'date':'2026-11-03', 'time':'09:00', 'plan':'B'},
        {'_key':'FAKE-003', 'selfPayDate':'2026-11-05', 'selfPayTime':'14:30',
         '_pureSelfPay':True, 'plan':'BAD'},
    ]


def signed_headers(*, secret=SECRET, stamp=None, nonce=None, path=producer.PATH):
    stamp = stamp or str(int(time.time()))
    nonce = nonce or secrets.token_urlsafe(30)
    import hmac, hashlib
    sig = hmac.new(secret.encode(),f'GET\n{path}\n{stamp}\n{nonce}'.encode('ascii'),hashlib.sha256).hexdigest()
    return {'X-DOUBTS-Timestamp':stamp,'X-DOUBTS-Nonce':nonce,
            'X-DOUBTS-Signature':sig}


@pytest.fixture
def source_client(monkeypatch):
    monkeypatch.setenv('SHANLIN_V362_SYNTHETIC_ONLY','1')
    monkeypatch.setenv('SHANLIN_V362_SERVICE_SECRET', SECRET)
    producer._seen.clear()
    app=FastAPI()
    app.include_router(producer.create_router(synthetics))
    with TestClient(app) as client:
        yield client
    producer._seen.clear()


def test_source_disabled_default(monkeypatch):
    monkeypatch.delenv('SHANLIN_V362_SYNTHETIC_ONLY',raising=False)
    app=FastAPI()
    app.include_router(producer.create_router(synthetics))
    with TestClient(app) as c:
        assert c.get(producer.PATH).status_code==423


def test_source_requires_distinct_new_service_secret(monkeypatch):
    monkeypatch.setenv('SHANLIN_V362_SYNTHETIC_ONLY','1')
    monkeypatch.setenv('SHANLIN_V362_SERVICE_SECRET','weak')
    with TestClient(FastAPI()) as _: pass
    app=FastAPI();app.include_router(producer.create_router(synthetics))
    with TestClient(app) as c:
        assert c.get(producer.PATH).status_code==503


def test_source_no_auth_rejected(source_client):
    assert source_client.get(producer.PATH).status_code==401


def test_valid_signed_request_synthetic_only(source_client):
    r=source_client.get(producer.PATH,headers=signed_headers())
    assert r.status_code==200
    payload=r.json()
    assert payload['clinicId']=='shanlin'
    assert payload['sourceTag']==producer.TAG
    assert payload['count']==3
    assert payload['bookingWritesEnabled'] is False
    assert payload['capacityVerified'] is False
    assert payload['isSynthetic'] is True
    assert payload['byKind']==[{'kind':'checkup','count':2},
                               {'kind':'self_pay_only','count':1}]
    assert payload['slotCounts'][0]['bookedCount']==2
    assert r.headers['cache-control'].startswith('no-store')


def test_no_patient_identity_on_wire(source_client):
    r=source_client.get(producer.PATH,headers=signed_headers())
    body=r.text
    for secret in ('FAKE PERSON','FAKE PHONE','FAKE ID','FAKE LINE','FAKE NOTE',
                   'FAKE-001','name','idNumber','lineUserId'):
        assert secret not in body
    assert 'appointments' not in r.json()


def test_wrong_secret_rejected(source_client):
    r=source_client.get(producer.PATH,headers=signed_headers(secret='incorrect-other-secret-and-long-enough-for-testing-123'))
    assert r.status_code==401


def test_signed_wrong_path_rejected(source_client):
    r=source_client.get(producer.PATH,headers=signed_headers(path='/api/other'))
    assert r.status_code==401


def test_replay_rejected(source_client):
    headers=signed_headers()
    assert source_client.get(producer.PATH,headers=headers).status_code==200
    assert source_client.get(producer.PATH,headers=headers).status_code==409


@pytest.mark.parametrize('age',[-200,200])
def test_timestamps_rejected(source_client,age):
    r=source_client.get(producer.PATH,headers=signed_headers(stamp=str(int(time.time())+age)))
    assert r.status_code==401


def test_bad_nonce_rejected(source_client):
    r=source_client.get(producer.PATH,headers=signed_headers(nonce='tiny'))
    assert r.status_code==401


def test_source_only_get(source_client):
    assert source_client.post(producer.PATH,headers=signed_headers()).status_code==405
    assert source_client.delete(producer.PATH).status_code==405


def test_source_refuses_wrong_shape():
    with pytest.raises(HTTPException) as e:
        producer.summarize_synthetic_rows({'appointments':[]})
    assert e.value.status_code==503


def test_producer_no_capacity_inference():
    r=producer.summarize_synthetic_rows(synthetics())
    assert all(slot['capacity'] is None and slot['availabilityConfirmed'] is False
               for slot in r['slotCounts'])


def test_source_rows_ceiling():
    with pytest.raises(HTTPException):
        producer.summarize_synthetic_rows([{}]*1001)


def test_consumer_disabled_by_default(monkeypatch):
    monkeypatch.delenv('PILOT_V362_SYNTHETIC_READ_ENABLED',raising=False)
    with pytest.raises(HTTPException) as e:
        consumer.read_synthetic_summary()
    assert e.value.status_code==423


def test_consumer_rejects_weak_secret(monkeypatch):
    monkeypatch.setenv('PILOT_V362_SYNTHETIC_READ_ENABLED','1')
    monkeypatch.setenv('PILOT_V362_SERVICE_SECRET','short')
    with pytest.raises(HTTPException) as e:
        consumer.read_synthetic_summary()
    assert e.value.status_code==503


def test_consumer_fixed_loopback_endpoint():
    assert consumer.ENDPOINT=='http://127.0.0.1:8017/api/integration/v362/booking-summary'
    assert consumer.integration_contract()['productionReadEnabled'] is False
    assert consumer.integration_contract()['individualStaffRolesVerified'] is False


def test_consumer_validation_allows_source_summary():
    value=consumer._validate(producer.summarize_synthetic_rows(synthetics()))
    assert value['count']==3


@pytest.mark.parametrize('change',[{'clinicId':'yidian'}, {'mode':'production'},
                                    {'isSynthetic':False}, {'capacityVerified':True},
                                    {'containsPatientIdentity':True},
                                    {'bookingWritesEnabled':True}, {'remindersEnabled':True},
                                    {'unknownPatientName':'Mary'}])
def test_consumer_rejects_untrusted_contract(change):
    fake=producer.summarize_synthetic_rows(synthetics())
    fake.update(change)
    with pytest.raises(HTTPException) as e:consumer._validate(fake)
    assert e.value.status_code==503


def test_consumer_rejects_inconsistent_counts():
    fake=producer.summarize_synthetic_rows(synthetics())
    fake['byPlan'][0]['count']=99
    with pytest.raises(HTTPException):consumer._validate(fake)


def test_consumer_rejects_private_slot_fields():
    fake=producer.summarize_synthetic_rows(synthetics())
    fake['slotCounts'][0]['phone']='FAKE'
    with pytest.raises(HTTPException):consumer._validate(fake)


def test_consumer_rejects_forged_capacity():
    fake=producer.summarize_synthetic_rows(synthetics())
    fake['slotCounts'][0]['capacity']=30
    with pytest.raises(HTTPException):consumer._validate(fake)


def test_consumer_rejects_wrong_plan_type():
    fake=producer.summarize_synthetic_rows(synthetics())
    fake['byPlan'][0]['plan']=['A']
    with pytest.raises(HTTPException):consumer._validate(fake)


@pytest.fixture
def clinic_gateway(monkeypatch):
    mock_console=types.ModuleType('platform_console')
    mock_console.NO_CACHE={'Cache-Control':'no-store'}
    def local_only(request):
        if request.client.host not in ('127.0.0.1','testclient'):
            raise HTTPException(403)
    def platform_read(request: Request):
        if request.headers.get('x-test-role')!='engineer':
            raise HTTPException(401)
        return {'role':'platform_admin'}
    mock_console.platform_read=platform_read
    mock_console.local_only=local_only
    monkeypatch.setitem(sys.modules,'platform_console',mock_console)
    mock_backend=types.ModuleType('pilot_backend')
    def require_clinic(request:Request):
        role=request.headers.get('x-test-role')
        if role is None or role=='engineer':raise HTTPException(401)
        return {'role':'clinic_admin','clinic': 'yidian' if role=='yidian' else 'shanlin',
                'legacyConfig': {'name':'山林診所'} if role=='shanlin' else None}
    mock_backend.require_clinic=require_clinic
    monkeypatch.setitem(sys.modules,'pilot_backend',mock_backend)
    sys.modules.pop('platform_shanlin_booking_routes_v362',None)
    routes=importlib.import_module('platform_shanlin_booking_routes_v362')
    monkeypatch.setattr(routes,'read_synthetic_summary',lambda: {'clinicId':'shanlin', 'mode':'synthetic_only','count':4})
    app=FastAPI(); app.include_router(routes.router)
    with TestClient(app) as client:
        yield client,routes
    sys.modules.pop('platform_shanlin_booking_routes_v362',None)


def test_clinic_gateway_roles(clinic_gateway):
    client,_=clinic_gateway
    path='/api/pilot/admin/shanlin/booking/v362/summary'
    assert client.get(path).status_code==401
    assert client.get(path,headers={'x-test-role':'engineer'}).status_code==401
    assert client.get(path,headers={'x-test-role':'yidian'}).status_code==403
    assert client.get(path,headers={'x-test-role':'unverified'}).status_code==409
    r=client.get(path+'?clinic=yidian',headers={'x-test-role':'shanlin'})
    assert r.status_code==200 and r.json()['clinicId']=='shanlin'


def test_engineer_only_synthetic_summary(clinic_gateway):
    client,_=clinic_gateway
    path='/api/pilot/platform/booking/v362/synthetic-summary'
    assert client.get(path).status_code==401
    assert client.get(path,headers={'x-test-role':'shanlin'}).status_code==401
    assert client.get(path,headers={'x-test-role':'engineer'}).status_code==200


def test_contract_metadata_only_engineer(clinic_gateway):
    client,_=clinic_gateway
    path='/api/pilot/platform/booking/v362/contract'
    assert client.get(path).status_code==401
    result=client.get(path,headers={'x-test-role':'engineer'})
    assert result.status_code==200
    assert result.json()['individualStaffRolesVerified'] is False


def test_no_write_routes(clinic_gateway):
    client,routes=clinic_gateway
    assert all(item.methods=={'GET'} for item in routes.router.routes)
    assert client.post('/api/pilot/admin/shanlin/booking/v362/summary').status_code==405


def test_app_clone_v361_preserved(monkeypatch):
    original=FastAPI()
    @original.get('/prior-v361')
    def prior():return {'ok':True}
    module=types.ModuleType('integrated_app_platform_v361');module.app=original
    monkeypatch.setitem(sys.modules,'integrated_app_platform_v361',module)
    new=types.ModuleType('platform_shanlin_booking_routes_v362')
    from fastapi import APIRouter
    new.router=APIRouter()
    @new.router.get('/new-v362')
    def newroute():return {'ok':True}
    monkeypatch.setitem(sys.modules,'platform_shanlin_booking_routes_v362',new)
    sys.modules.pop('integrated_app_platform_v362',None)
    app=importlib.import_module('integrated_app_platform_v362').app
    assert app is not original
    assert any(x.path=='/prior-v361' for x in app.routes)
    assert any(x.path=='/new-v362' for x in app.routes)
    assert not any(x.path=='/new-v362' for x in original.routes)
    sys.modules.pop('integrated_app_platform_v362',None)


def test_install_add_only_contract():
    assert all('v362' in name for name in installer.FILES)
    assert all('main.py' not in name and 'index.html' not in name for name in installer.FILES)
    assert len(installer.FILES)==7


def test_install_refuses_conflicts(tmp_path):
    a=tmp_path/installer.FILES[0]
    a.parent.mkdir(parents=True)
    a.write_text('custom')
    errors,_=installer.inspect(tmp_path)
    assert any('overwrite' in e for e in errors)


def test_install_idempotent_and_preserves_existing(tmp_path):
    for rel in installer.REQUIRED:
        f=tmp_path/rel
        f.parent.mkdir(parents=True,exist_ok=True)
        f.write_text('pass\n')
    original=(tmp_path/installer.REQUIRED[0]).read_bytes()
    assert installer.apply(tmp_path)[0]==[]
    assert installer.apply(tmp_path)[0]==[]
    assert (tmp_path/installer.REQUIRED[0]).read_bytes()==original
    assert all((tmp_path/rel).is_file() for rel in installer.FILES)


def test_no_production_secrets_in_sources():
    for rel in installer.FILES[:5]:
        text=(ROOT/rel).read_text()
        assert 'FIREBASE_CREDENTIALS' not in text
        assert 'ADMIN_PASSWORD' not in text
        assert 'shanlin-bot-production.up.railway.app' not in text
