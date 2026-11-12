"""Platform 8006 v3.5 queries only sanitized remote status, never dispatches."""
import sys
from pathlib import Path
import json
from fastapi.testclient import TestClient
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'website'))
from integrated_app_platform_v35 import app
import platform_line_bridge_v35 as bridge
import pilot_backend as backend

API='/api/pilot/platform/console/line-bot/v35/status'

@pytest.fixture(autouse=True)
def clear():
    backend._sessions.clear();backend._failed.clear()
    yield
    backend._sessions.clear();backend._failed.clear()

def engineer():
    client=TestClient(app)
    token=backend.new_session(None,role='platform_admin',username='user')
    client.cookies.set(backend.COOKIE,token,path='/api/pilot')
    return client

def test_v35_routes_preserve_previous_modules():
    with TestClient(app) as c:
        assert c.get('/platform/modules').status_code==200
        assert 'module-center-v35.js' in c.get('/platform/modules').text
        assert 'line-status-v35.js' in c.get('/platform/modules/appointment_reminders/line-status').text
        assert 'v3.5 安全排程與發送紀錄' in c.get('/platform/modules/appointment_reminders/line-status').text
        assert c.get('/platform/modules/appointment_reminders/release').status_code==200
        assert c.get('/platform/assets/module-release-v33.js').status_code==200
        for file in ('module-center-v35.js','line-status-v35.js'):
            assert c.get('/platform/assets/'+file).status_code==200
        code=c.get('/platform/assets/line-status-v35.js').text
        assert 'api/reminder/v35/run' not in code and 'X-Reminder-Status-Token' not in code
        assert 'lineUserId' not in code and 'POST' not in code
        assert '電話綁定' in c.get('/platform/assets/module-center-v35.js').text


def test_status_login_required_and_no_send_methods():
    with TestClient(app) as c:
        assert c.get(API).status_code in (401,403)
        assert c.post(API).status_code==405
        assert c.post('/api/reminder/v35/run').status_code==404
        assert c.post('/api/reminder/send').status_code==404


def test_no_secret_means_no_network(monkeypatch):
    monkeypatch.delenv('PLATFORM_SHANLIN_V35_STATUS_TOKEN',raising=False)
    def no_network(*args,**kwargs):raise AssertionError('no network allowed')
    monkeypatch.setattr(bridge.urllib.request,'build_opener',no_network)
    with engineer() as c:
        r=c.get(API)
        assert r.status_code==200
        assert r.json()['state']=='not_configured'
        assert r.json()['lastRun'] is None


def test_remote_results_are_redacted_and_read_only(monkeypatch):
    monkeypatch.setenv('PLATFORM_SHANLIN_V35_STATUS_TOKEN','x'*40)
    raw={'schema':35,'clinicId':'shanlin','sendEnabled':False,
         'lastRun':{'mode':'preview','targetDate':'2026-10-25','runAtUtc':'2026-10-24T10:00:00Z',
                    'eligible':2,'accepted':0,'phone':'0912345678','lineUserId':'U'+'c'*32,
                    'name':'PRIVATE_NAME'}}
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def read(self,limit):return json.dumps(raw).encode('utf-8')
    class Opener:
        def open(self,request,timeout):
            assert request.get_method()=='GET'
            assert request.full_url==bridge.STATUS_URL
            assert request.get_header('X-reminder-status-token')=='x'*40
            return Response()
    monkeypatch.setattr(bridge.urllib.request,'build_opener',lambda *args:Opener())
    with engineer() as c:
        r=c.get(API)
        assert r.status_code==200
        payload=r.json()
        assert payload['state']=='connected'
        assert payload['sendEnabled'] is False
        assert payload['schedulerVerified'] is False
        assert '0912345678' not in r.text and 'PRIVATE_NAME' not in r.text
        assert 'lineUserId' not in r.text and 'xxxx' not in r.text
        assert r.headers['Cache-Control']=='no-store'


def test_invalid_remote_source_fails_closed(monkeypatch):
    monkeypatch.setenv('PLATFORM_SHANLIN_V35_STATUS_TOKEN','x'*40)
    class R:
        status=200
        def __enter__(self):return self
        def __exit__(self,*x):pass
        def read(self,_):return b'{"schema":35,"clinicId":"yidian","sendEnabled":true}'
    class O:
        def open(self,*args,**kwargs):return R()
    monkeypatch.setattr(bridge.urllib.request,'build_opener',lambda *x:O())
    assert bridge.check_status()['state']=='unverified'
    assert bridge._NoRedirect().redirect_request(None,None,302,'',{},'https://evil.example') is None
