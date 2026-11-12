"""Unified Shanlin/Yidian login regression tests. Offline-only; no real secrets or data."""
from collections import defaultdict, deque
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

SITE=Path(__file__).resolve().parents[1]/'website'
sys.path.insert(0,str(SITE))
from integrated_app_home_restored import app  # noqa: E402
import pilot_backend as backend  # noqa: E402


@pytest.fixture
def isolate(monkeypatch,tmp_path):
    monkeypatch.setattr(backend,'PRIVATE_DIR',tmp_path)
    monkeypatch.setattr(backend,'_failed',defaultdict(deque))
    monkeypatch.setattr(backend,'_sessions',{})
    monkeypatch.setenv('PILOT_STORAGE','local-demo')
    monkeypatch.setenv('PILOT_YIDIAN_STORAGE','local-demo')
    return monkeypatch


def test_same_visible_account_and_password_fields_for_both_clinics():
    with TestClient(app) as client:
        page=client.get('/pilot?clinic=shanlin&view=admin')
        assert page.status_code==200
        login=page.text.split('<section id="adminLogin"',1)[1].split('</section>',1)[0]
        assert 'id="shanlinLoginUsername"' in login
        assert 'id="shanlinLoginPassword"' in login
        assert 'id="yidianLoginUsername"' in login
        assert 'id="yidianLoginPassword"' in login
        assert 'placeholder="例如：shanlin_admin"' in login
        assert login.count('>管理帳號<input')==2
        assert login.count('>管理密碼<input')==2
        assert 'source-note clinic-login-info' not in login
        assert 'id="yidianAccountNotice" class="small-note" role="status" hidden' in login
        assert 'Firebase' not in login


def test_both_browser_forms_use_one_shared_api():
    with TestClient(app) as client:
        script=client.get('/pilot/assets/pilot.js')
        assert script.status_code==200
        js=script.text
        assert "request('/admin/login'" in js
        assert '/admin/legacy-shanlin-login' not in js
        assert "shanlinLoginUsername':'yidianLoginUsername" in js
        assert 'clinicId:loggingClinic,username,password' in js
        assert 'loginInFlight' in js


def test_retired_password_only_api_rejected_before_calling_railway(isolate):
    called=[]
    isolate.setattr(backend,'verify_shanlin_legacy',lambda p:called.append(p) or True)
    with TestClient(app) as client:
        res=client.post('/api/pilot/admin/legacy-shanlin-login',json={'password':'fake-example'})
        assert res.status_code==422
        assert called==[]
        assert client.get('/api/pilot/admin/session').status_code==401


def test_wrong_shanlin_username_cannot_use_correct_password(isolate):
    called=[]
    isolate.setattr(backend,'verify_shanlin_legacy',lambda p:called.append(p) or True)
    with TestClient(app) as client:
        for name in ('other_admin','yidian_admin','shanlin_legacy'):
            res=client.post('/api/pilot/admin/login',json={
                'clinicId':'shanlin','username':name,'password':'fake-example',
            })
            assert res.status_code==401
            assert res.json()['detail']=='帳號或密碼不正確'
        assert called==[]
        assert client.get('/api/pilot/admin/session').status_code==401


def test_verified_shanlin_username_and_real_password_bridge(isolate):
    calls=[]
    def password_ok(password):
        calls.append(('password',password))
        return password=='fake-correct'
    def clinic_config(password):
        calls.append(('config',password))
        return backend.default_config('shanlin'),''
    isolate.setattr(backend,'verify_shanlin_legacy',password_ok)
    isolate.setattr(backend,'fetch_shanlin_clinic_config',clinic_config)
    with TestClient(app) as client:
        response=client.post('/api/pilot/admin/login',json={
            'clinicId':'shanlin','username':'shanlin_admin','password':'fake-correct',
        })
        assert response.status_code==200
        assert response.json()['clinicId']=='shanlin'
        state=client.get('/api/pilot/admin/session')
        assert state.status_code==200
        assert state.json()['username']=='shanlin_admin'
        assert state.json()['clinicId']=='shanlin'
        assert calls==[('password','fake-correct'),('config','fake-correct')]
        assert client.get('/api/pilot/admin/integration').json()['legacyConfigRead'] is True


def test_wrong_shanlin_password_keeps_401_and_does_not_fetch_config(isolate):
    calls=[]
    isolate.setattr(backend,'verify_shanlin_legacy',lambda p: False)
    isolate.setattr(backend,'fetch_shanlin_clinic_config',lambda p:calls.append(p))
    with TestClient(app) as client:
        response=client.post('/api/pilot/admin/login',json={
            'clinicId':'shanlin','username':'shanlin_admin','password':'wrong-fake',
        })
        assert response.status_code==401
        assert calls==[]
        assert client.get('/api/pilot/admin/session').status_code==401


def test_rate_limit_still_applies_to_wrong_usernames(isolate):
    isolate.setattr(backend,'verify_shanlin_legacy',lambda p: pytest.fail('Network must not be called'))
    with TestClient(app) as client:
        for _ in range(10):
            response=client.post('/api/pilot/admin/login',json={
                'clinicId':'shanlin','username':'wrong_admin','password':'bad',
            })
            assert response.status_code==401
        assert client.post('/api/pilot/admin/login',json={
            'clinicId':'shanlin','username':'shanlin_admin','password':'fake-correct',
        }).status_code==429


def test_legacy_endpoint_also_requires_correct_username(isolate):
    isolate.setattr(backend,'verify_shanlin_legacy',lambda p: pytest.fail('Must not call Railway'))
    with TestClient(app) as client:
        response=client.post('/api/pilot/admin/legacy-shanlin-login',json={
            'username':'yidian_admin','password':'fake-correct',
        })
        assert response.status_code==401


def test_yidian_existing_account_still_works_and_is_separate(isolate):
    backend.provision_yidian_account('yidian_admin','fake-very-long-yidian-password')
    with TestClient(app) as client:
        response=client.post('/api/pilot/admin/login',json={
            'clinicId':'yidian','username':'yidian_admin',
            'password':'fake-very-long-yidian-password',
        })
        assert response.status_code==200
        assert response.json()['clinicId']=='yidian'
        assert client.get('/api/pilot/admin/session').json()['clinicId']=='yidian'
        bad=client.post('/api/pilot/admin/login',json={
            'clinicId':'yidian','username':'shanlin_admin',
            'password':'fake-very-long-yidian-password',
        })
        assert bad.status_code==401


def test_shanlin_fails_closed_on_source_identity_mismatch(isolate):
    isolate.setattr(backend,'verify_shanlin_legacy',lambda p:True)
    isolate.setattr(backend,'fetch_shanlin_clinic_config',lambda p:(None,'clinic mismatch'))
    with TestClient(app) as client:
        response=client.post('/api/pilot/admin/login',json={
            'clinicId':'shanlin','username':'shanlin_admin','password':'fake-correct',
        })
        assert response.status_code==409
        assert client.get('/api/pilot/admin/session').status_code==401
