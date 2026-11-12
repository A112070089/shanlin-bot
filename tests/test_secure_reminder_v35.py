import asyncio
import copy
from datetime import datetime, timedelta
from pathlib import Path
import importlib.util
import os
import threading
import sys

import pytest
from fastapi import HTTPException, FastAPI
from fastapi.testclient import TestClient

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'shanlin_bot'))
import reminder_secure_v35 as mod

class FakeDB:
    def __init__(self,data=None):
        self.data=copy.deepcopy(data or {})
        self.lock=threading.RLock()
        self.claims=[]
    def reference(self,path):return Ref(self,path.split('/'))

class Ref:
    def __init__(self,database,keys):self.db=database;self.keys=keys
    def child(self,key): return Ref(self.db,self.keys+[str(key)])
    def _parent(self,create=False):
        base=self.db.data
        for key in self.keys[:-1]:
            if create: base=base.setdefault(key,{})
            else: base=base.get(key,{})
        return base
    def get(self):
        with self.db.lock:
            return copy.deepcopy(self._parent().get(self.keys[-1]))
    def set(self,value):
        with self.db.lock:self._parent(True)[self.keys[-1]]=copy.deepcopy(value)
    def update(self,value):
        with self.db.lock:
            dest=self._parent(True).setdefault(self.keys[-1],{})
            dest.update(copy.deepcopy(value))
    def transaction(self, callback):
        with self.db.lock:
            parent=self._parent(True)
            previous=copy.deepcopy(parent.get(self.keys[-1]))
            changed=callback(previous)
            parent[self.keys[-1]]=copy.deepcopy(changed)
            return copy.deepcopy(changed)

GOOD='U'+'a'*32
NOW=datetime(2026,10,24,18,5,tzinfo=mod.TAIPEI)
DATE=(NOW.date()+timedelta(days=1)).isoformat()
SECRET='A'*48


def settings(live=False, **kw):
    s=dict(job_token=SECRET,status_token='B'*48,hash_secret='C'*48,channel_token='D'*48,
           live_enabled=live,start_hour=17,end_hour=21,limit=50)
    s.update(kw)
    return mod.Settings(**s)


def fake(verified=True, key='x', **kwargs):
    record={'date':DATE,'time':'09:00','lineUserId':GOOD,'lineBindingVerified':verified,
            'name':'SECRET_PATIENT_NAME', 'phone':'0912345678','idNumber':'A123456789'}
    if verified:
        record['lineBindingProofV35']=mod.binding_proof(settings().hash_secret,key,GOOD)
    record.update(kwargs)
    return record


def go(coro): return asyncio.run(coro)


def test_preview_never_sends_and_no_claim(monkeypatch):
    fb=FakeDB({'appointments':{'A123456789':fake(key='A123456789'),'x':fake(verified=False)}})
    async def send(*args): raise AssertionError('preview must not send')
    report=go(mod.execute('preview',settings(),database=fb,now=NOW,sender=send))
    assert report['eligible']==1 and report['unverifiedBinding']==1 and report['accepted']==0
    assert fb.reference('reminder_v35/claims').get() is None
    assert fb.reference('reminder_v35/last_run').get()['mode']=='preview'


def test_live_disabled_by_default_even_with_data():
    fb=FakeDB({'appointments':{'x':fake()}})
    with pytest.raises(HTTPException) as exc:go(mod.execute('dispatch',settings(),now=NOW,database=fb))
    assert exc.value.status_code==409
    assert fb.reference('reminder_v35').get() is None


def test_schedule_window_enforced():
    fb=FakeDB({'appointments':{'x':fake()}})
    with pytest.raises(HTTPException) as exc:go(mod.execute('dispatch',settings(live=True),now=NOW.replace(hour=7),database=fb))
    assert exc.value.status_code==409


def test_strong_credentials_required():
    fb=FakeDB({'appointments':{'x':fake()}})
    with pytest.raises(HTTPException) as exc:go(mod.execute('dispatch',settings(live=True,hash_secret='short'),now=NOW,database=fb))
    assert exc.value.status_code==503


def test_dedupe_and_no_personal_identifiers_in_logs():
    fb=FakeDB({'appointments':{'A123456789':fake(key='A123456789')}})
    calls=[]
    async def send(_cfg,user,text,retry):
        calls.append((user,text,retry));return 'accepted',200
    first=go(mod.execute('dispatch',settings(live=True),now=NOW,database=fb,sender=send))
    second=go(mod.execute('dispatch',settings(live=True),now=NOW,database=fb,sender=send))
    assert first['accepted']==1 and second['duplicateSkipped']==1 and len(calls)==1
    assert '禁食禁水' not in calls[0][1]
    assert 'SECRET_PATIENT_NAME' not in calls[0][1]
    reminder_log=str(fb.data['reminder_v35'])
    assert 'A123456789' not in reminder_log
    assert '0912345678' not in reminder_log
    assert GOOD not in reminder_log
    assert 'SECRET_PATIENT_NAME' not in reminder_log
    assert len(next(iter(fb.data['reminder_v35']['claims'])))==64
    assert 'LINE' not in calls[0][1].splitlines()[0]  # basic plain reminder text


def test_live_skips_legacy_unverified_binding():
    fb=FakeDB({'appointments':{'x':fake(verified=False)}})
    async def forbidden(*args):raise AssertionError('should not send unverified binding')
    report=go(mod.execute('dispatch',settings(live=True),now=NOW,database=fb,sender=forbidden))
    assert report['eligible']==0 and report['unverifiedBinding']==1
    assert not fb.data['reminder_v35'].get('claims')

@pytest.mark.parametrize('override',[{'status':'已取消'},{'appointmentStatus':'cancelled'},{'status':'confirmed','appointmentStatus':'cancelled'},
                                    {'cancelled':True},{'date':'2026-12-31'},
                                    {'lineUserId':'fake'}])
def test_invalid_or_cancelled_appointments_ignored(override):
    fb=FakeDB({'appointments':{'x':fake(**override)}})
    report=go(mod.execute('preview',settings(),now=NOW,database=fb))
    assert report['eligible']==0


def test_atomic_claim_one_sender_under_parallel_runs():
    fb=FakeDB({'appointments':{'x':fake()}})
    count=[]
    async def send(*args):count.append(args);return 'accepted',200
    def one():return go(mod.execute('dispatch',settings(live=True),now=NOW,database=fb,sender=send))
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as pool:
        result=list(pool.map(lambda _:one(),range(2)))
    assert sum(x['accepted'] for x in result)==1 and len(count)==1


def test_line_409_accepted_only_when_accepted_request_id(monkeypatch):
    class Resp:
        status_code=409
        def __init__(self,accepted):self.headers={'x-line-accepted-request-id':'xyz'} if accepted else {}
    class Client:
        def __init__(self,*args,**kw):self.accepted=True
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,url,headers,json):
            assert headers['X-Line-Retry-Key'].count('-')==4
            assert url==mod.API
            assert 'SECRET_PATIENT_NAME' not in str(json)
            return Resp(True)
    monkeypatch.setattr(mod.httpx,'AsyncClient',Client)
    result=go(mod._line_push(settings(live=True),GOOD,'hello','11111111-2222-3333-4444-555555555555'))
    assert result==('accepted',409)


def test_cancelled_during_run_does_not_send():
    fb=FakeDB({'appointments':{'x':fake()}})
    class MutatingDB(FakeDB):pass
    original_claim=mod._claim
    def mutate_claim(claims,key,run_id,t):
        claim=original_claim(claims,key,run_id,t)
        fb.reference('appointments/x').update({'status':'已取消'})
        return claim
    old=mod._claim
    try:
        mod._claim=mutate_claim
        async def forbidden(*a):raise AssertionError('cancelled after claim must skip')
        report=go(mod.execute('dispatch',settings(live=True),now=NOW,database=fb,sender=forbidden))
        assert report['changedSkipped']==1
    finally:mod._claim=old


def test_unauthenticated_secret_and_status():
    app=FastAPI();app.include_router(mod.router)
    client=TestClient(app)
    # Short/missing secret fails closed without accessing Firebase.
    with pytest.MonkeyPatch.context() as m:
        m.delenv('REMINDER_V35_JOB_SECRET',raising=False)
        m.delenv('REMINDER_V35_STATUS_TOKEN',raising=False)
        assert client.post('/api/reminder/v35/run',json={'mode':'preview'}).status_code==503
        assert client.get('/api/reminder/v35/status').status_code==503
        m.setenv('REMINDER_V35_JOB_SECRET',SECRET)
        assert client.post('/api/reminder/v35/run',json={'mode':'preview'},headers={'X-Reminder-Job-Token':'wrong'}).status_code==401


def test_source_patch_preserves_other_routes_and_is_idempotent():
    spec=importlib.util.spec_from_file_location('patcher',BASE/'scripts'/'apply_shanlin_bot_v35.py')
    patcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(patcher)
    source='''from fastapi import FastAPI, HTTPException\napp = FastAPI()\n@app.post("/webhook")\nasync def webhook():\n    return {"ok": True}\n@app.post("/api/reminder/send")\nasync def send_reminders():\n    db.reference("appointments").get()\n    await push_message('U',[])\n    return {"sent":1}\n@app.get("/")\nasync def root():\n    return {"status":"ok"}\n'''
    changed=patcher.rewrite(source)
    assert 'status_code=410' in changed
    assert 'async def webhook()' in changed and 'async def root()' in changed
    assert patcher.rewrite(changed)==changed
    import ast;ast.parse(changed)
    with pytest.raises(ValueError):patcher.rewrite(source.replace('await push_message', 'await skip_message'))


def test_legacy_booking_cannot_swap_line_recipient_while_reusing_verified_flag():
    changed=fake(lineUserId='U'+'b'*32)
    assert changed['lineBindingVerified'] is True
    assert mod._verified_binding(changed,'x',settings()) is False
    fb=FakeDB({'appointments':{'x':changed}})
    async def forbidden(*args):raise AssertionError('forged recipient')
    report=go(mod.execute('dispatch',settings(live=True),now=NOW,database=fb,sender=forbidden))
    assert report['unverifiedBinding']==1 and report['accepted']==0


def test_other_appointment_key_cannot_reuse_binding_proof():
    proof=mod.binding_proof(settings().hash_secret,'key-1',GOOD)
    record=fake(key='key-1')
    assert proof==record['lineBindingProofV35']
    assert not mod._verified_binding(record,'key-2',settings())


def test_secure_binding_uses_line_api_identity_not_client_user_id(monkeypatch):
    # Real LINE network is not contacted in this simulated test.
    fb=FakeDB({'appointments':{'A123456789':fake(verified=False)}})
    monkeypatch.setenv('REMINDER_V35_HASH_SECRET','C'*48)
    monkeypatch.setenv('REMINDER_V35_LIFF_CHANNEL_ID','2010169963')
    monkeypatch.setattr(mod,'_db',lambda:fb)
    async def fake_line_identity(token,ch):
        assert token=='valid-access-token-'+'x'*36 and ch=='2010169963'
        return GOOD
    monkeypatch.setattr(mod,'_verified_line_user',fake_line_identity)
    with TestClient(FastAPI()) as c: pass
    app=FastAPI();app.include_router(mod.router)
    client=TestClient(app)
    r=client.post('/api/reminder/v35/binding/verify',json={
        'id_number':'A123456789','phone':'0912345678',
        'line_access_token':'valid-access-token-'+'x'*36})
    assert r.status_code==200,r.text
    updated=fb.reference('appointments/A123456789').get()
    assert updated['lineUserId']==GOOD and mod._verified_binding(updated,'A123456789',settings())
    assert 'A123456789' not in r.text and '0912345678' not in r.text and GOOD not in r.text
    # No LINE API push involved, does not touch patient reminder claims.
    assert fb.reference('reminder_v35/claims').get() is None


def test_binding_wrong_phone_fails_without_writing_verified_proof(monkeypatch):
    fb=FakeDB({'appointments':{'A123456789':fake(verified=False)}})
    monkeypatch.setenv('REMINDER_V35_HASH_SECRET','C'*48)
    monkeypatch.setenv('REMINDER_V35_LIFF_CHANNEL_ID','2010169963')
    monkeypatch.setattr(mod,'_db',lambda:fb)
    async def verified(*a):return GOOD
    monkeypatch.setattr(mod,'_verified_line_user',verified)
    app=FastAPI();app.include_router(mod.router)
    r=TestClient(app).post('/api/reminder/v35/binding/verify',json={
        'id_number':'A123456789','phone':'0912999999','line_access_token':'x'*40})
    assert r.status_code==403 and 'lineBindingProofV35' not in fb.reference('appointments/A123456789').get()


def test_send_limit_skips_old_claims_but_processes_unclaimed_appointments():
    fb=FakeDB({'appointments':{'one':fake(key='one'),'two':fake(key='two')}})
    attempts=[]
    async def send(*args):attempts.append(args);return 'accepted',200
    a=go(mod.execute('dispatch',settings(live=True,limit=1),now=NOW,database=fb,sender=send))
    b=go(mod.execute('dispatch',settings(live=True,limit=1),now=NOW,database=fb,sender=send))
    assert a['accepted']==1 and b['accepted']==1 and b['duplicateSkipped']==1
    assert len(attempts)==2


def test_verified_binding_rate_limited_per_line_user(monkeypatch):
    fb=FakeDB({'appointments':{'A123456789':fake(verified=False)}})
    monkeypatch.setenv('REMINDER_V35_HASH_SECRET','C'*48)
    monkeypatch.setenv('REMINDER_V35_LIFF_CHANNEL_ID','2010169963')
    monkeypatch.setattr(mod,'_db',lambda:fb)
    async def verified(*a):return GOOD
    monkeypatch.setattr(mod,'_verified_line_user',verified)
    app=FastAPI();app.include_router(mod.router)
    client=TestClient(app)
    payload={'id_number':'A123456789','phone':'0912345678','line_access_token':'x'*40}
    assert all(client.post('/api/reminder/v35/binding/verify',json=payload).status_code==200 for i in range(5))
    assert client.post('/api/reminder/v35/binding/verify',json=payload).status_code==429
    assert '0912345678' not in str(fb.data['reminder_v35'])
