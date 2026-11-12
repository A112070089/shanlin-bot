"""Offline contract tests: NEVER open a real Firebase, Railway or LINE connection."""
from __future__ import annotations

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
import secrets
import sys
from threading import Lock
import time
import types
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT/'shanlin_booking_stage'
V363 = ROOT/'shanlin_v363_staging'
if not V363.is_dir(): V363 = ROOT.parent/'doubts_current_audit'/'shanlin_v363_staging'
for folder in (STAGE, V363, ROOT/'website', (ROOT.parent/'doubts_current_audit'/'website') if (ROOT.parent/'doubts_current_audit'/'website').is_dir() else ROOT.parent/'website'):
    if str(folder) not in sys.path: sys.path.insert(0,str(folder))
from booking_transactions import BookingStore

DAY = (datetime.now(ZoneInfo('Asia/Taipei')).date()+timedelta(days=30)).isoformat()
DAY2 = (datetime.now(ZoneInfo('Asia/Taipei')).date()+timedelta(days=31)).isoformat()
SECRET = 'only-for-test-hmac-secret-should-be-long-enough-abc1234'
HOST = 'doubts-shanlin-test-default-rtdb.firebaseio.com'


@pytest.fixture(autouse=True)
def test_only_env(monkeypatch):
    monkeypatch.setenv('SHANLIN_V363_STAGING_ENABLED','1')
    monkeypatch.setenv('SHANLIN_V365_SYNTHETIC_WRITE_ENABLED','1')
    monkeypatch.setenv('SHANLIN_V363_TEST_FIREBASE_HOST',HOST)
    monkeypatch.setenv('FIREBASE_URL',f'https://{HOST}/')
    monkeypatch.delenv('FIREBASE_CREDENTIALS',raising=False)


def root_data():
    return {'booking_config':{'clinic':{
        'clinicId':'shanlin','name':'山林診所','integrationV363TestOnly':True,
        'elderlyDates':[DAY,DAY2], 'elderlyTimes':['09:00','10:00'],
        'capacityBySlot':{DAY:{'09:00':1,'10:00':2},DAY2:{'09:00':2,'10:00':2}}
    }},'appointments':{},'self_pay_booking':{},'unrelated':{'x':'must survive transaction'}}


class MemoryRef:
    def __init__(self,db,key): self.db=db;self.key=key
    def get(self):
        with self.db.lock:
            if self.key=='/': return deepcopy(self.db.root)
            cur=self.db.root
            for p in self.key.strip('/').split('/'):
                cur=cur.get(p) if isinstance(cur,dict) else None
            return deepcopy(cur)
    def transaction(self,callback):
        assert self.key=='/'  # A single RTDB CAS spans BOTH booking nodes.
        with self.db.lock:
            outcome=callback(deepcopy(self.db.root))
            self.db.root=deepcopy(outcome)
            self.db.commits+=1
            return deepcopy(outcome)
    def set(self,*args):raise AssertionError('No set() outside atomic transaction')
    def update(self,*args):raise AssertionError('No update() outside atomic transaction')
    def delete(self,*args):raise AssertionError('No deletion of medical records')


class MemoryDb:
    def __init__(self,root=None):
        self.root=deepcopy(root if root is not None else root_data())
        self.lock=Lock();self.commits=0
    def reference(self,name):return MemoryRef(self,name)


def booking(phone='0912345678',date=DAY,time='09:00',**extra):
    return {'name':'純虛構測試人員','phone':phone,'plan':'A','date':date,'time':time, **extra}


def error_code(call):
    with pytest.raises(HTTPException) as e:call()
    return e.value.status_code


def test_create_and_list_are_original_nodes_not_duplicate_backend():
    db=MemoryDb();store=BookingStore(db)
    added=store.change('create',booking())
    assert added['status']=='success' and added['isSynthetic'] is True
    assert db.root['appointments'][added['key']]['clinicId']=='shanlin'
    assert db.root['appointments'][added['key']]['doubtsSyntheticV363'] is True
    assert db.root['unrelated']=={'x':'must survive transaction'}
    assert db.commits==1
    assert store.list()['appointments'][0]['_key']==added['key']


def test_only_one_concurrent_winner_for_last_slot():
    db=MemoryDb();store=BookingStore(db)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=[]
        futures=[pool.submit(store.change,'create',booking(phone=p))
                 for p in ('0912345678','0923456789')]
        for f in futures:
            try:results.append(f.result()['status'])
            except HTTPException as exc:results.append(exc.status_code)
    assert sorted(results,key=str)==sorted(['success',409],key=str)
    assert len(db.root['appointments'])==1 and db.commits==1


def test_cancellation_releases_slot_preserves_history_and_line_reminder_guard():
    db=MemoryDb();store=BookingStore(db)
    one=store.change('create',booking())
    assert error_code(lambda:store.change('create',booking(phone='0923456789')))==409
    done=store.change('cancel',{'expectedRevision':one['revision']},one['key'])
    row=db.root['appointments'][one['key']]
    assert done['action']=='cancel' and row['status']=='cancelled'
    assert row['cancelled'] is True and row['name']=='純虛構測試人員'
    two=store.change('create',booking(phone='0923456789'))
    assert two['key'] != one['key']
    assert error_code(lambda:store.change('update',{'name':'重新啟用','expectedRevision':done['revision']},one['key']))==409


def test_reschedule_capacity_and_optimistic_concurrency():
    db=MemoryDb();store=BookingStore(db)
    a=store.change('create',booking())
    new=store.change('update',{'date':DAY2,'time':'09:00','expectedRevision':a['revision']},a['key'])
    assert db.root['appointments'][a['key']]['date']==DAY2
    assert error_code(lambda:store.change('update',{'date':DAY,'time':'09:00','expectedRevision':a['revision']},a['key']))==409
    assert new['revision']!=a['revision']
    # The original slot is now available again.
    store.change('create',booking(phone='0923456789'))


def test_rejected_update_cannot_overwrite_any_record():
    db=MemoryDb();store=BookingStore(db)
    old=store.change('create',booking())
    before=deepcopy(db.root)
    assert error_code(lambda:store.change('update',{'phone':'invalid','expectedRevision':old['revision']},old['key']))==422
    assert db.root==before
    assert error_code(lambda:store.change('update',{'date':DAY2,'time':'11:00','expectedRevision':old['revision']},old['key']))==409
    assert db.root==before


def test_selfpay_only_reduces_capacity():
    data=root_data()
    data['self_pay_booking']['SP01']={'doubtsSyntheticV363':True,'clinicId':'shanlin',
        'name':'另一位合成病患','phone':'0911111111','selfPayDate':DAY,'selfPayTime':'09:00'}
    store=BookingStore(MemoryDb(data))
    assert error_code(lambda:store.change('create',booking(phone='0923456789')))==409


def test_checkup_and_selfpay_same_person_same_slot_count_once():
    data=root_data()
    data['booking_config']['clinic']['capacityBySlot'][DAY]['09:00']=2
    data['appointments']['A01']={'doubtsSyntheticV363':True,'name':'測試','phone':'0911111111',
        'date':DAY,'time':'09:00','plan':'A'}
    data['self_pay_booking']['SP01']={'doubtsSyntheticV363':True,'name':'測試','phone':'0911111111',
        'selfPayDate':DAY,'selfPayTime':'09:00'}
    store=BookingStore(MemoryDb(data))
    store.change('create',booking(phone='0923456789'))  # 2 slots, not 3
    assert error_code(lambda:store.change('create',booking(phone='0934567890')))==409


def test_update_existing_checkup_paired_to_selfpay_is_not_falsely_blocked():
    raw=root_data()
    raw['appointments']['A01']={'name':'合成搭配自費','phone':'0911111111',
        'date':DAY,'time':'09:00','plan':'A','doubtsSyntheticV363':True}
    raw['self_pay_booking']['S01']={'name':'相同受檢者','phone':'0911111111',
        'selfPayDate':DAY,'selfPayTime':'09:00','doubtsSyntheticV363':True}
    store=BookingStore(MemoryDb(raw))
    current=store.list()['appointments'][0]
    changed=store.change('update',{'name':'修改合成資料','expectedRevision':current['_revision']},'A01')
    assert changed['status']=='success'


def test_original_admin_combines_checkup_plus_selfpay_into_one_display_row():
    raw=root_data()
    raw['appointments']['A01']={'name':'合成搭配自費','phone':'0911111111',
        'date':DAY,'time':'09:00','plan':'A','doubtsSyntheticV363':True}
    raw['self_pay_booking']['S01']={'name':'相同受檢者','phone':'0911111111',
        'selfPayDate':DAY,'selfPayTime':'09:00','selfPayItems':[{'name':'合成自費項目'}],
        'selfPayTotal':100,'doubtsSyntheticV363':True}
    rows=BookingStore(MemoryDb(raw)).list()['appointments']
    assert len(rows)==1
    assert rows[0]['_key']=='A01' and rows[0]['_hasSelfPay'] is True
    assert rows[0]['selfPayItems']==['合成自費項目']
    assert rows[0]['selfPayTotal']==100


def test_original_admin_keeps_unmatched_selfpay_visible():
    raw=root_data()
    raw['self_pay_booking']['S01']={'name':'合成純自費','phone':'0911111111',
        'selfPayDate':DAY,'selfPayTime':'09:00','doubtsSyntheticV363':True}
    rows=BookingStore(MemoryDb(raw)).list()['appointments']
    assert len(rows)==1
    assert rows[0]['_pureSelfPay'] is True and rows[0]['_key']=='SELFPAY::S01'



def test_ambiguous_selfpay_linkage_fail_closed():
    raw=root_data()
    raw['booking_config']['clinic']['capacityBySlot'][DAY]['09:00']=5
    for key in ('A01','B02'):
        raw['appointments'][key]={'name':'合成家人','phone':'0911111111','plan':'A',
            'date':DAY,'time':'09:00','doubtsSyntheticV363':True}
    raw['self_pay_booking']['S01']={'name':'合成自費','phone':'0911111111',
        'selfPayDate':DAY,'selfPayTime':'09:00','doubtsSyntheticV363':True}
    store=BookingStore(MemoryDb(raw))
    assert error_code(lambda:store.change('create',booking(phone='0934567890')))==409



def test_duplicate_phone_refused_across_all_origins():
    db=MemoryDb();store=BookingStore(db)
    store.change('create',booking())
    assert error_code(lambda:store.change('create',booking(date=DAY2,time='10:00')))==409


@pytest.mark.parametrize('tamper',[
    lambda d:d['booking_config']['clinic'].update({'integrationV363TestOnly':False}),
    lambda d:d['booking_config']['clinic'].update({'clinicId':'yidian'}),
    lambda d:d['appointments'].update({'A01':{'name':'REAL PATIENT'}}),
    lambda d:d['self_pay_booking'].update({'A02':{'clinicId':'yidian','doubtsSyntheticV363':True}}),
    lambda d:d['booking_config']['clinic'].pop('capacityBySlot'),
])
def test_unsafe_database_or_unset_capacity_fails_closed(tamper):
    raw=root_data();tamper(raw);db=MemoryDb(raw);store=BookingStore(db)
    code=error_code(lambda:store.change('create',booking()))
    assert code in (409,503) and db.commits==0


def test_disabled_flag_and_prod_database_rejected_even_if_requested(monkeypatch):
    monkeypatch.syspath_prepend(str(V363)); monkeypatch.syspath_prepend(str(STAGE))
    monkeypatch.delenv('SHANLIN_V363_STAGING_ENABLED',raising=False)
    path=STAGE/'booking_api.py'
    spec=importlib.util.spec_from_file_location('_disabled_stage_api',path)
    with pytest.raises(RuntimeError,match='disabled'):spec.loader.exec_module(importlib.util.module_from_spec(spec))
    monkeypatch.setenv('SHANLIN_V363_STAGING_ENABLED','1')
    monkeypatch.setenv('FIREBASE_URL','https://shanlin-clinic-default-rtdb.firebaseio.com/')
    monkeypatch.setenv('SHANLIN_V363_TEST_FIREBASE_HOST','shanlin-clinic-default-rtdb.firebaseio.com')
    spec2=importlib.util.spec_from_file_location('_prod_stage_api',path)
    with pytest.raises(RuntimeError,match='TEST Firebase'):spec2.loader.exec_module(importlib.util.module_from_spec(spec2))


@pytest.fixture
def api_client(monkeypatch):
    monkeypatch.syspath_prepend(str(V363));monkeypatch.syspath_prepend(str(STAGE))
    monkeypatch.setenv('SHANLIN_V363_STAGING_ENABLED','1')
    monkeypatch.setenv('SHANLIN_V363_READ_ENABLED','1')
    monkeypatch.setenv('SHANLIN_V365_SYNTHETIC_WRITE_ENABLED','1')
    monkeypatch.setenv('SHANLIN_V363_SERVICE_SECRET',SECRET)
    monkeypatch.setenv('FIREBASE_URL',f'https://{HOST}/')
    monkeypatch.setenv('SHANLIN_V363_TEST_FIREBASE_HOST',HOST)
    monkeypatch.delenv('FIREBASE_CREDENTIALS',raising=False)
    db=MemoryDb()
    monkeypatch.setitem(sys.modules,'main',types.SimpleNamespace(db=db))
    source_path=STAGE/'booking_api.py'
    spec=importlib.util.spec_from_file_location('_test_stage_api',source_path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with TestClient(module.app) as client: yield client,db,module


def sign(method,path,body=b'',stamp=None,nonce=None):
    stamp=stamp or str(int(time.time()));nonce=nonce or secrets.token_urlsafe(26)
    digest=hashlib.sha256(body).hexdigest()
    message=f'{method}\n{path}\n{stamp}\n{nonce}\n{digest}'.encode()
    mac=hmac.new(SECRET.encode(),message,hashlib.sha256).hexdigest()
    return {'X-DOUBTS-Timestamp':stamp,'X-DOUBTS-Nonce':nonce,'X-DOUBTS-Signature':mac}


def test_real_fastapi_routes_with_signed_requests(api_client):
    client,db,_=api_client
    path='/api/integration/v365/appointments'
    assert client.get(path).status_code==401
    ok=client.get(path,headers=sign('GET',path))
    assert ok.status_code==200 and ok.json()['isSynthetic'] is True
    payload=json.dumps(booking(),separators=(',',':')).encode()
    headers={**sign('POST',path,payload),'Content-Type':'application/json'}
    r=client.post(path,content=payload,headers=headers)
    assert r.status_code==200,r.text
    assert client.post(path,content=payload,headers=headers).status_code==409  # replay
    assert client.post(path,content=b'{}',headers=sign('POST',path,payload)).status_code==401  # body change
    assert client.post('/api/admin/import').status_code==404
    assert client.post('/api/reminder/send').status_code==404
    assert client.post('/api/appointment/book').status_code==404
    assert client.get('/docs').status_code==404
    assert db.commits==1


def test_staging_http_modifications_and_no_non_admin_secrets(api_client):
    client,db,_=api_client
    path='/api/integration/v365/appointments'
    body=json.dumps(booking(),separators=(',',':')).encode()
    added=client.post(path,content=body,headers={**sign('POST',path,body),'Content-Type':'application/json'}).json()
    edit_path=path+'/'+added['key']
    edit_data={'date':DAY2,'time':'09:00','expectedRevision':added['revision']}
    raw=json.dumps(edit_data,separators=(',',':')).encode()
    updated=client.patch(edit_path,content=raw,headers={**sign('PATCH',edit_path,raw),'Content-Type':'application/json'})
    assert updated.status_code==200,updated.text
    rev=updated.json()['revision']
    cancelled={'expectedRevision':rev}
    raw=json.dumps(cancelled,separators=(',',':')).encode()
    res=client.request('DELETE',edit_path,content=raw,headers={**sign('DELETE',edit_path,raw),'Content-Type':'application/json'})
    assert res.status_code==200,res.text
    assert db.root['appointments'][added['key']]['cancelled'] is True


def test_test_write_flag_off(api_client,monkeypatch):
    client,db,_=api_client
    monkeypatch.setenv('SHANLIN_V365_SYNTHETIC_WRITE_ENABLED','0')
    path='/api/integration/v365/appointments'
    assert client.get(path,headers=sign('GET',path)).status_code==423
    assert db.commits==0


def test_platform_scoped_to_verified_shanlin_and_origin(monkeypatch):
    from platform_shanlin_booking_stage import router,API_ROOT
    import pilot_backend as backend
    from fastapi import FastAPI
    app=FastAPI();app.include_router(router)
    ok={'clinic':'shanlin','role':'clinic_admin','legacyConfig':{'name':'山林診所'},'csrf':'abc'}
    app.dependency_overrides[backend.require_clinic]=lambda: ok
    app.dependency_overrides[backend.require_clinic_mutation]=lambda: ok
    monkeypatch.setenv('PILOT_V365_SYNTHETIC_BOOKINGS_ENABLED','1')
    monkeypatch.setattr('platform_shanlin_booking_stage._relay',lambda *a,**kw:{'isSynthetic':True,'clinicId':'shanlin','appointments':[]})
    with TestClient(app) as c:
        path=API_ROOT+'/appointments'
        assert c.get(path).status_code==200
        assert c.post(path,json=booking()).status_code==403
        assert c.post(path,json=booking(),headers={'Origin':'http://testserver'}).status_code==200
        app.dependency_overrides[backend.require_clinic]=lambda: {**ok,'clinic':'yidian'}
        assert c.get(path).status_code==403
        app.dependency_overrides[backend.require_clinic]=lambda: {**ok,'role':'platform_admin'}
        assert c.get(path).status_code==403


def test_hardening_original_admin_no_external_piiscript():
    html=(ROOT/'website/shanlin_admin_booking_stage.html').read_text('utf-8')
    assert 'shanlin-bot-production.up.railway.app' not in html
    assert 'JSON.stringify(a).replace' not in html
    assert 'X-Admin-Password' not in html
    assert 'booking-stage/appointments' in html
    assert 'expectedRevision' in html
    assert '僅供山林診所合成資料交易測試' in html
