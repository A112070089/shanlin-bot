"""v3.6.4 official-source merge tests. Synthetic data, no network or real Firebase."""
from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
import secrets
import sys
import time
import types

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / 'shanlin_v364_candidate'


def load_installer():
    path=ROOT/'scripts/install_official_candidate_v364.py'
    spec=importlib.util.spec_from_file_location('_doubts_v364_install',path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_source_pinned_to_reviewed_commit_and_patch():
    doc=json.loads((CANDIDATE/'MANIFEST.json').read_text(encoding='utf-8'))
    assert doc['pinned_railway_commit']=='1b5714783bd8e0b6f6396fcb7fc8384e6f990387'
    assert doc['official_main_sha256']=='de3c75b6fbda11db0bddc5f1d37ce07ede0eec36b65212cd50bccbfc35909b51'
    assert hashlib.sha256((CANDIDATE/'main.py').read_bytes()).hexdigest()==doc['candidate_main_sha256']
    stage=(ROOT/'shanlin_v363_staging/main.py').read_text(encoding='utf-8')
    assert (CANDIDATE/'main.py').read_text(encoding='utf-8') in stage


@pytest.mark.parametrize('entry',['main.py','reminder_secure_v35.py','liff-appt.html','liff-verify.html',
                                  'admin.html','shanlin-demo.html','shanlin_v363_readonly.py','app_readonly_v364.py'])
def test_candidate_files_match_manifest(entry):
    doc=json.loads((CANDIDATE/'MANIFEST.json').read_text(encoding='utf-8'))
    data=(CANDIDATE/entry).read_bytes()
    assert hashlib.sha256(data).hexdigest()==doc['candidate_file_sha256'][entry]


def test_pinned_li_f_f_uses_verified_tokens_no_legacy_id():
    booking=(CANDIDATE/'liff-appt.html').read_text(encoding='utf-8')
    binding=(CANDIDATE/'liff-verify.html').read_text(encoding='utf-8')
    assert 'liff.getAccessToken()' in booking
    assert 'liff.getAccessToken()' in binding
    assert '/api/appointment/book' in booking
    assert '/api/reminder/v35/binding/verify' in binding
    assert '/api/liff/verify' not in binding
    assert 'line_access_token' in booking and 'line_access_token' in binding
    assert 'line_user_id:' not in booking
    assert 'testUserId' not in binding


def test_old_endpoints_disabled_in_security_candidate():
    text=(CANDIDATE/'main.py').read_text(encoding='utf-8')
    assert "status_code=410" in text
    assert 'if not CHANNEL_SECRET:' in text
    assert 'lineBindingVerified' in (CANDIDATE/'reminder_secure_v35.py').read_text(encoding='utf-8')
    assert 'from reminder_secure_v35 import router' in text


def test_candidate_is_test_only_without_env(monkeypatch):
    monkeypatch.syspath_prepend(str(CANDIDATE))
    monkeypatch.delenv('SHANLIN_V363_STAGING_ENABLED',raising=False)
    path=CANDIDATE/'app_readonly_v364.py'
    spec=importlib.util.spec_from_file_location('_doubts_v364_disabled_test',path)
    mod=importlib.util.module_from_spec(spec)
    with pytest.raises(RuntimeError,match='disabled'):
        spec.loader.exec_module(mod)


def test_known_production_firebase_rejected(monkeypatch):
    monkeypatch.syspath_prepend(str(CANDIDATE))
    monkeypatch.setenv('SHANLIN_V363_STAGING_ENABLED','1')
    monkeypatch.setenv('FIREBASE_URL','https://shanlin-clinic-default-rtdb.firebaseio.com/')
    monkeypatch.setenv('SHANLIN_V363_TEST_FIREBASE_HOST','shanlin-clinic-default-rtdb.firebaseio.com')
    spec=importlib.util.spec_from_file_location('_doubts_v364_prod_reject',CANDIDATE/'app_readonly_v364.py')
    mod=importlib.util.module_from_spec(spec)
    with pytest.raises(RuntimeError,match='TEST Firebase'):
        spec.loader.exec_module(mod)


class FakeRef:
    def __init__(self,path,nodes):self.path=path;self.nodes=nodes
    def get(self):
        if self.path not in {'booking_config/clinic','appointments','self_pay_booking'}:
            raise AssertionError('Unexpected DB node')
        return self.nodes.get(self.path)
    def set(self,*a,**kw):raise AssertionError('Write attempted')
    def update(self,*a,**kw):raise AssertionError('Write attempted')
    def transaction(self,*a,**kw):raise AssertionError('Write attempted')
    def delete(self,*a,**kw):raise AssertionError('Write attempted')


class FakeDb:
    def __init__(self):
        self.nodes={
            'booking_config/clinic':{'name':'山林診所','clinicId':'shanlin','integrationV363TestOnly':True},
            'appointments':{'SYN-01':{'name':'DO NOT PRINT PRIVATE NAME','phone':'0900000000',
                        'doubtsSyntheticV363':True,'plan':'A','date':'2026-11-08','time':'09:00'}},
            'self_pay_booking':{},
        }
    def reference(self,key):return FakeRef(key,self.nodes)


@pytest.fixture
def live_candidate_client(monkeypatch):
    monkeypatch.syspath_prepend(str(CANDIDATE))
    host='doubts-shanlin-test-default-rtdb.firebaseio.com'
    secret='local-secret-test-only-very-long-and-not-for-deployment-12345'
    monkeypatch.setenv('SHANLIN_V363_STAGING_ENABLED','1')
    monkeypatch.setenv('SHANLIN_V363_READ_ENABLED','1')
    monkeypatch.setenv('SHANLIN_V363_SERVICE_SECRET',secret)
    monkeypatch.setenv('FIREBASE_URL',f'https://{host}/')
    monkeypatch.setenv('SHANLIN_V363_TEST_FIREBASE_HOST',host)
    monkeypatch.setenv('SHANLIN_ALLOWED_ORIGINS','')
    monkeypatch.delenv('FIREBASE_CREDENTIALS',raising=False)
    fb=types.ModuleType('firebase_admin')
    fb._apps={}
    fb.initialize_app=lambda *a,**kw: (_ for _ in ()).throw(AssertionError('Firebase init forbidden'))
    fb.credentials=types.SimpleNamespace(Certificate=lambda *a: (_ for _ in ()).throw(AssertionError('Firebase credential use')))
    fb.db=FakeDb()
    monkeypatch.setitem(sys.modules,'firebase_admin',fb)
    monkeypatch.setitem(sys.modules,'firebase_admin.db',fb.db)
    from shanlin_v363_readonly import _seen
    _seen.clear()
    path=CANDIDATE/'app_readonly_v364.py'
    spec=importlib.util.spec_from_file_location('_doubts_v364_test_readonly_instance',path)
    mod=importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules,spec.name,mod)
    spec.loader.exec_module(mod)
    with TestClient(mod.app) as client:
        yield client,secret
    _seen.clear()


def signed(secret):
    ts=str(int(time.time()))
    nonce=secrets.token_urlsafe(32)
    path='/api/integration/v363/booking-summary'
    signature=hmac.new(secret.encode(),f'GET\n{path}\n{ts}\n{nonce}'.encode('ascii'),hashlib.sha256).hexdigest()
    return {'X-DOUBTS-Timestamp':ts,'X-DOUBTS-Nonce':nonce,'X-DOUBTS-Signature':signature}


def test_signed_summary_returns_no_patient_identifiers(live_candidate_client):
    client,secret=live_candidate_client
    resp=client.get('/api/integration/v363/booking-summary',headers=signed(secret))
    assert resp.status_code==200,resp.text
    assert resp.json()['clinicId']=='shanlin'
    assert resp.json()['count']==1
    assert resp.json()['isSynthetic'] is True
    assert resp.json()['bookingWritesEnabled'] is False
    assert resp.json()['capacityVerified'] is False
    for blocked in ['PRIVATE NAME','0900000000','SYN-01','phone','lineUserId']:
        assert blocked not in resp.text


def test_no_signature_no_data(live_candidate_client):
    client,_=live_candidate_client
    assert client.get('/api/integration/v363/booking-summary').status_code==401


@pytest.mark.parametrize('method,path',[('POST','/api/appointment/book'),('POST','/api/liff/verify'),
        ('POST','/api/reminder/send'),('POST','/webhook'),('GET','/api/admin/appointments'),
        ('POST','/api/admin/import'),('GET','/admin.html'),('GET','/docs')])
def test_mutating_or_legacy_routes_are_not_exposed(live_candidate_client,method,path):
    client,_=live_candidate_client
    assert client.request(method,path).status_code==404


def test_installer_add_only_and_conflict_fail_closed(tmp_path):
    inst=load_installer()
    for rel in inst.PINNED_PREREQS:
        src=ROOT/rel
        dst=tmp_path/rel
        dst.parent.mkdir(parents=True,exist_ok=True)
        dst.write_bytes(src.read_bytes())
    original=tmp_path/'shanlin_v363_staging/main.py'
    original_before=original.read_bytes()
    data,errors,actions=inst.preflight(tmp_path)
    assert not errors,errors
    assert all('Would add:' in a for a in actions)
    errors,_=inst.install(tmp_path)
    assert not errors,errors
    assert original.read_bytes()==original_before
    assert (tmp_path/'shanlin_v364_candidate/main.py').read_bytes()==(CANDIDATE/'main.py').read_bytes()
    errors,_=inst.install(tmp_path)
    assert not errors
    (tmp_path/'shanlin_v364_candidate/main.py').write_text('ALTERED')
    errors, _=inst.install(tmp_path)
    assert errors and 'overwrite' in errors[0]
    assert original.read_bytes()==original_before
