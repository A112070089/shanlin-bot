"""Local-only regressions for dual-clinic login/route changes.

Never makes network requests to Railway or Firebase. All login credentials and
pilot private paths in tests are fake and temporary.
"""
from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
import sys

from fastapi.testclient import TestClient
import pytest

SITE = Path(__file__).resolve().parents[1] / 'website'
sys.path.insert(0, str(SITE))

from integrated_app_home_restored import app  # noqa: E402
import pilot_backend as pb  # noqa: E402

OFFICIAL = 'https://shanlin-bot-production.up.railway.app/admin.html'


@pytest.fixture
def isolated_auth(monkeypatch, tmp_path):
    monkeypatch.setattr(pb, 'PRIVATE_DIR', tmp_path)
    monkeypatch.setattr(pb, '_failed', defaultdict(deque))
    monkeypatch.setattr(pb, '_sessions', {})
    monkeypatch.delenv('PILOT_YIDIAN_FIREBASE_URL', raising=False)
    monkeypatch.delenv('PILOT_YIDIAN_FIREBASE_CREDENTIALS', raising=False)
    monkeypatch.setenv('PILOT_YIDIAN_STORAGE', 'local-demo')
    return tmp_path


def test_shanlin_link_stays_on_verified_external_origin():
    with TestClient(app) as c:
        page = c.get('/pilot?clinic=shanlin&view=admin')
        assert page.status_code == 200
        assert 'href="' + OFFICIAL + '"' in page.text
        assert 'href="/admin.html"' not in page.text
        script = c.get('/pilot/assets/pilot.js')
        assert script.status_code == 200
        assert OFFICIAL in script.text
        assert "'山林登入已停止：'" not in script.text
        assert "state.legacyConfigRead===true" in script.text


def test_login_form_appearance_is_shared_but_credentials_are_separate():
    with TestClient(app) as c:
        page = c.get('/pilot?clinic=yidian&view=admin')
        assert page.status_code == 200
        html = page.text
        assert html.count('登入診所管理後台</button>') == 2
        assert '<h1 id="adminLoginTitle">診所管理員登入</h1>' in html
        assert 'id="shanlinLoginPassword"' in html
        assert 'id="yidianLoginUsername"' in html
        assert 'id="yidianLoginPassword"' in html
        assert 'id="shanlinLoginError"' in html
        assert 'id="yidianLoginError"' in html
        assert 'Firebase 尚未開通' not in html


def test_frontend_can_classify_errors_and_avoids_double_submit():
    with TestClient(app) as c:
        src = c.get('/pilot/assets/pilot.js').text
        for token in ('error.status=r.status', 'err.status===401', 'err.status===429',
                      'err.status===409', 'err.status===503', 'loginInFlight',
                      "$('yidianLoginError')", "$('shanlinLoginError')"):
            assert token in src, token
        assert '山林登入已停止：' not in src


def test_yidian_pilot_status_unconfigured_is_not_misreported_as_firebase_off(isolated_auth):
    with TestClient(app) as c:
        r = c.get('/api/pilot/clinics/yidian/account-status')
        assert r.status_code == 200
        data = r.json()
        assert data['accountProvisioned'] is False
        assert data['pilotStorage'] == 'local-demo'
        assert data['firebaseConnectionVerified'] is False
        assert data['firebaseConnected'] is None
        assert data['pilotFirebaseCredentialsProvided'] is False
        assert '無法由此判斷 Firebase 專案是否已建立' in data['notice']


def test_yidian_configured_unverified_status_never_connects(monkeypatch, isolated_auth):
    monkeypatch.setenv('PILOT_YIDIAN_FIREBASE_URL', 'https://dummy.invalid')
    monkeypatch.setenv('PILOT_YIDIAN_FIREBASE_CREDENTIALS', 'fake-test-key-not-a-secret')
    monkeypatch.setenv('PILOT_YIDIAN_STORAGE', 'firebase')
    with TestClient(app) as c:
        data = c.get('/api/pilot/clinics/yidian/account-status').json()
        assert data['pilotStorage'] == 'firebase'
        assert data['pilotFirebaseCredentialsProvided'] is True
        assert data['firebaseConnectionVerified'] is False
        assert '尚未驗證' in data['notice']
    # No attempted Firebase read or external network call.


def test_shanlin_wrong_password_is_401_and_rate_limit_is_preserved(monkeypatch, isolated_auth):
    monkeypatch.setattr(pb, 'verify_shanlin_legacy', lambda password: False)
    with TestClient(app) as c:
        for _ in range(10):
            r = c.post('/api/pilot/admin/legacy-shanlin-login', json={'password':'wrong-test'})
            assert r.status_code == 401
            assert r.json()['detail'] == '帳號或密碼不正確'
        r = c.post('/api/pilot/admin/legacy-shanlin-login', json={'password':'wrong-test'})
        assert r.status_code == 429
    # We did not disable protection to make the error message friendlier.


def test_shanlin_ownership_mismatch_denies_session(monkeypatch, isolated_auth):
    monkeypatch.setattr(pb, 'verify_shanlin_legacy', lambda password: True)
    monkeypatch.setattr(pb, 'fetch_shanlin_clinic_config',
                        lambda password: (None, '後台回傳診所歸屬不一致'))
    with TestClient(app) as c:
        r = c.post('/api/pilot/admin/legacy-shanlin-login', json={'password':'placeholder'})
        assert r.status_code == 409
        assert not c.cookies.get(pb.COOKIE)
        assert c.get('/api/pilot/admin/integration').status_code == 401


def test_shanlin_verified_login_returns_official_url_not_yidian(monkeypatch, isolated_auth):
    monkeypatch.setattr(pb, 'verify_shanlin_legacy', lambda password: True)
    mock = pb.default_config('shanlin')
    mock['phone'] = '02-0000-0000'
    monkeypatch.setattr(pb, 'fetch_shanlin_clinic_config',
                        lambda password: (mock, ''))
    with TestClient(app) as c:
        r = c.post('/api/pilot/admin/legacy-shanlin-login', json={'password':'placeholder'})
        assert r.status_code == 200
        assert r.json()['clinicId'] == 'shanlin'
        session = c.get('/api/pilot/admin/session').json()
        assert session['clinicId'] == 'shanlin'
        integration = c.get('/api/pilot/admin/integration').json()
        assert integration['legacyConfigRead'] is True
        assert integration['url'] == OFFICIAL
        assert '127.0.0.1:5500' not in str(integration)


def test_yidian_accounts_are_independent_of_shanlin(monkeypatch, isolated_auth):
    pb.provision_yidian_account('yidian_demo_admin', 'test_only_very_long_password')
    with TestClient(app) as c:
        status = c.get('/api/pilot/clinics/yidian/account-status').json()
        assert status['accountProvisioned'] is True
        wrong = c.post('/api/pilot/admin/login', json={
            'clinicId':'shanlin','username':'yidian_demo_admin',
            'password':'test_only_very_long_password',
        })
        assert wrong.status_code == 409
        ok = c.post('/api/pilot/admin/login', json={
            'clinicId':'yidian','username':'yidian_demo_admin',
            'password':'test_only_very_long_password',
        })
        assert ok.status_code == 200
        assert ok.json()['clinicId'] == 'yidian'
        assert c.get('/api/pilot/admin/session').json()['clinicId'] == 'yidian'


def test_no_legacy_admin_rewrite_in_integration_layer():
    src = (SITE / 'integrated_site.py').read_text(encoding='utf-8')
    assert '"https://shanlin-bot-production.up.railway.app/admin.html", "/admin.html"' not in src
    assert '"http://127.0.0.1:5500/admin.html", "/admin.html"' not in src
    assert 'integrated_pilot_js' in src


def test_frontend_uses_neutral_account_status_wording():
    js = (SITE / 'pilot_static' / 'pilot.js').read_text(encoding='utf-8')
    assert '頤典 Firebase 尚未開通' not in js
    assert '也沒有頤典 Firebase' not in js
    assert '登入已停止' not in js
    assert '請稍後再試' in js
