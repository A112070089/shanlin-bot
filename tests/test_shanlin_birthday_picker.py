"""Regression guards: Shanlin synthetic DOB picker, no backend or production changes."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / 'website/shanlin_patient_field_validation.js').read_text(encoding='utf-8')
SERVER = (ROOT / 'website/integrated_app_platform_patient_stage.py').read_text(encoding='utf-8')
HTML = (ROOT / 'website/appointment2.html').read_text(encoding='utf-8')


def test_original_booking_form_is_untouched():
    assert 'name="birthday"' in HTML
    assert 'id="bookingForm"' in HTML
    assert 'shanlin-dob-picker' not in HTML
    assert 'shanlin_patient_field_validation.js' in SERVER


def test_ios_native_wheel_and_gregorian_roc_conversion():
    assert "(pointer: coarse)" in JS
    assert "select.size = wheelSize" in JS
    assert "selects.year" in JS and "selects.month" in JS and "selects.day" in JS
    assert "latestYear = today.getFullYear() - 65" in JS
    assert "new Date(y, m, 0).getDate()" in JS
    assert "const roc = year - 1911" in JS
    assert "original.type = 'hidden'" in JS
    assert "String(roc).padStart(2, '0')" in JS
    assert "original.dispatchEvent(new Event('input'" in JS
    assert '西元／民國對照' in JS


def test_name_validation_and_synthetic_safety_remain_separate():
    assert 'NORMAL_NAME' in JS
    assert '注音、數字或符號' in JS
    assert 'FAKE_NAME.test(value)' in JS
    assert '本機測試僅接受指定的 DOUBTS 虛構測試姓名' in JS
    assert '本機測試僅允許虛構生日 450101 或 390101' in JS
    assert '本機合成測試尚未開放自費健檢預約' in JS
    assert "cache: 'no-store'" in JS
    assert 'displaySlotError()' in JS
    assert 'event.stopImmediatePropagation()' in JS
    assert 'form.dispatchEvent(new Event(' in JS
    assert "'birthday' ? birthdayPicker.selects.year" in JS
    assert '</script' not in JS.lower()
