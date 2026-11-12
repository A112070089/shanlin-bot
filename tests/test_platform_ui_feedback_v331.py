"""v3.3.1 UI regression checks. No Firebase or production state mutations."""
from pathlib import Path
import sys

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'website'))
from integrated_app_platform_v33 import app


def test_engineer_login_uses_object_safe_messages():
    with TestClient(app) as client:
        page = client.get('/platform/admin')
        assert page.status_code == 200
        assert 'platform-v321.js' in page.text
        js = client.get('/platform/assets/platform-v321.js')
        assert js.status_code == 200
        assert "error.status === 401" in js.text
        assert '帳號或密碼錯誤，請重新輸入。' in js.text
        assert "new Error(result.detail||" not in js.text
        assert 'function safeDetail' in js.text
        assert 'loginFeedback(loginErrorText(error),true)' in js.text


def test_login_error_is_visible_and_accessible():
    with TestClient(app) as client:
        css = client.get('/platform/assets/platform.css')
        assert css.status_code == 200
        assert '#loginMessage.error-alert' in css.text
        assert 'role="status"' in client.get('/platform/admin').text


def test_release_save_feedback_markup_and_scripts():
    with TestClient(app) as client:
        page = client.get('/platform/modules/appointment_reminders/release')
        assert page.status_code == 200
        assert 'progressSaveStatus' in page.text
        assert '✓ 已儲存進度' in page.text
        js = client.get('/platform/assets/module-release-v33.js')
        assert js.status_code == 200
        assert 'function updateSaveButtons' in js.text
        assert 'progressDirty()' in js.text
        assert 'checkSaved.add(savedCheck)' in js.text
        assert 'if(e.status===409) await reload()' in js.text


def test_saved_button_has_disabled_visual_style():
    with TestClient(app) as client:
        css = client.get('/platform/assets/module-release-v33.css')
        assert css.status_code == 200
        assert '#saveProgress:disabled' in css.text
        assert '.check-row form button:disabled' in css.text
        assert '.saved-note' in css.text


def test_release_data_stays_protected_by_engineer_session():
    with TestClient(app) as client:
        response = client.get('/api/pilot/platform/console/releases/appointment_reminders')
        assert response.status_code == 401
        assert response.headers.get('Content-Type', '').startswith('application/json')
