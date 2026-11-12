import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'website'))
from fastapi.testclient import TestClient
from integrated_app_platform import app
from platform_console_store import _default, CLINICS, FEATURES, clinic_entitlements


def test_local_ui_available():
    with TestClient(app) as c:
        r=c.get('/platform/admin')
        assert r.status_code==200 and '工程師登入' in r.text
        assert c.get('/platform/assets/platform.js').status_code==200
        assert c.get('/platform/assets/platform.css').status_code==200


def test_no_public_platform_data():
    with TestClient(app) as c:
        for path in ('/api/pilot/platform/console/state','/api/pilot/platform/console/health', '/api/pilot/platform/console/audit','/api/pilot/platform/console/session'):
            assert c.get(path).status_code in (401,403)
        assert c.post('/api/pilot/platform/console/features',json={'clinicId':'shanlin','featureId':'staff_worklist','enabled':True,'expectedRevision':'0'*32}).status_code in (401,403)


def test_external_client_cannot_get_login_ui():
    class External:
        def __init__(self,wrapped): self.wrapped=wrapped
        async def __call__(self,scope,receive,send):
            if scope['type']=='http':scope={**scope,'client':('203.0.113.9',1234)}
            return await self.wrapped(scope,receive,send)
    with TestClient(External(app)) as c:
        assert c.get('/platform/admin').status_code==403


def test_all_future_modules_not_deployed():
    for clinic in CLINICS:
        assert clinic_entitlements(clinic)['availableFeatures']==[]
    assert len(FEATURES)==3
    assert all(x is False for row in _default()['flags'].values() for x in row.values())


def test_clinic_login_cannot_access_platform():
    from pilot_backend import new_session,_sessions,sha256,COOKIE
    token=new_session('shanlin',role='clinic_admin',username='shanlin_admin')
    with TestClient(app) as c:
        c.cookies.set(COOKIE,token,path='/api/pilot')
        assert c.get('/api/pilot/platform/console/state').status_code==403
