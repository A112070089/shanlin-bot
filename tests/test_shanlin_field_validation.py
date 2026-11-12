"""Local-only Shanlin form validation. No database reads/writes in these tests."""
from pathlib import Path
import sys
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'website'))
import integrated_app_platform_patient_stage as patient


JS = (ROOT/'website'/'shanlin_patient_field_validation.js').read_text(encoding='utf-8')


def test_legacy_template_is_not_overwritten():
    original = (ROOT/'website'/'appointment2.html').read_text(encoding='utf-8')
    assert 'shanlin-patient-field-validation' not in original
    assert original.count('id="bookingForm"') == 1
    assert original.count('validateCaptcha()') >= 1


def test_shanlin_serves_inline_validation_only_on_scoped_page():
    with TestClient(patient.app) as client:
        r = client.get('/appointment2.html?clinic=shanlin&p=A')
        assert r.status_code == 200, r.text
        assert r.headers['x-clinic-id'] == 'shanlin'
        assert r.headers['referrer-policy'] == 'no-referrer'
        assert r.headers['cache-control'] == 'no-store'
        assert r.text.count('id="shanlin-patient-field-validation"') == 1
        assert 'X-DOUBTS-Patient-Test-Page' in r.text
        assert '/api/patient/shanlin/booking-test/confirm?clinic=shanlin' in r.text
        assert 'aria-invalid' in r.text
        assert '這個日期及時段已額滿' in r.text
        assert '自費' in r.text
        assert r.text.count('</body>') == 1
        assert client.get('/appointment2.html?clinic=yidian&p=A', follow_redirects=False).status_code == 303


def test_front_end_validation_separates_format_and_fake_identity():
    for fragment in ('請輸入正確的民國年月日', '高齡健檢須年滿65歲',
                     '身分證字號檢查碼不正確', '手機號碼須為09開頭的10位數字',
                     '本機測試僅允許', '不得使用真實姓名', '不得使用真實手機',
                     '無法讀取目前可預約時段', 'role', "form.noValidate = true",
                     'event.stopImmediatePropagation()', 'checkField', "form.dispatchEvent(new Event('submit'", "cache: 'no-store'"):
        assert fragment in JS, fragment
    assert 'eval(' not in JS and 'localStorage' not in JS
    assert r"/^09\d{8}$/" in JS


def test_missing_validation_asset_fails_closed(monkeypatch):
    import pathlib
    actual_is_file = pathlib.Path.is_file
    def is_file(p):
        if p.name == 'shanlin_patient_field_validation.js':
            return False
        return actual_is_file(p)
    monkeypatch.setattr(pathlib.Path, 'is_file', is_file)
    with TestClient(patient.app) as client:
        response=client.get('/appointment2.html?clinic=shanlin&p=A')
        assert response.status_code == 503
        assert '欄位驗證檔案遺失' in response.text
