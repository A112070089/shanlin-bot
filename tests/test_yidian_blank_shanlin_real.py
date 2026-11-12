"""Regression: Yidian must be genuinely empty; Shanlin owns existing source data.

No Firebase, patient records, TTS model calls or booking writes are performed.
"""
import sys
from html.parser import HTMLParser
from pathlib import Path

from fastapi.testclient import TestClient
from fastapi.responses import HTMLResponse

SITE = Path(__file__).resolve().parents[1] / 'website'
sys.path.insert(0, str(SITE))
from integrated_app_clinics import app
from integrated_app_voice import app as voice_stage_app
import integrated_clinic_routes as routes

client = TestClient(app)


class FormAudit(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = 0
        self.inputs = 0
        self.event_handlers = 0
        self.scripts = []
    def handle_starttag(self, tag, attrs):
        if tag == 'form': self.forms += 1
        if tag in ('input', 'textarea', 'select'): self.inputs += 1
        if tag == 'script': self.scripts.append(dict(attrs))
        self.event_handlers += sum(name.startswith('on') for name, _ in attrs)


def test_yidian_home_has_no_catalog_prices_or_source_scheme():
    html = client.get('/?clinic=yidian').text
    assert html.count('data-demo-empty="true"') == 3
    for text in ('A 方案', 'B 方案', 'C 方案', '腦肺方案', '腹部方案',
                 '骨密肌力方案', '115年臺北市', '胸部X光', '血液檢測',
                 '血脂肪檢查', '甲狀腺檢測', '山林', 'shanlin', 'NT$',
                 '來源參考價', '47 個', '101 個', '56 個'):
        assert text not in html, text
    assert '公版範例' in html
    assert '尚未建立方案' in html
    assert '尚未新增檢查細項、套組或價格' in html


def test_shanlin_is_the_only_home_with_real_catalog():
    sh = client.get('/?clinic=shanlin').text
    assert '山林現有自費加購項目' in sh
    assert '血脂肪檢查' in sh and '血液檢測' in sh
    assert 'NT$800（來源參考價）' in sh
    assert sh.count('class="shanlin-unit-row"') == 56
    assert '價格待核對（不可計價）' in sh
    assert '頤典公版' not in sh


def test_both_clinic_homepages_share_true_original_styles_and_sections():
    yi = client.get('/?clinic=yidian').text
    sh = client.get('/?clinic=shanlin').text
    for css in ('./assets/css/main.css', './assets/css/index.css?v=doubts-ui-v4',
                './yidian_senior_v14.css?v=15'):
        assert css in yi and css in sh
    for marker in ('id="header"', 'id="scrollspyHero"',
                   'class="elderly-plan-grid"', 'id="scrollspyFooter"',
                   'class="doubts-identity"'):
        assert marker in yi and marker in sh
    assert yi.count('class="elderly-plan-card"') == 3
    assert sh.count('class="elderly-plan-card"') == 3


def test_unscoped_and_scoped_old_booking_pages_never_show_shanlin_data_as_yidian():
    for url in ('/', '/index.html', '/appointment.html', '/appointment2.html',
                '/booking_success.html', '/search.html',
                '/appointment2.html?clinic=yidian&p=SELF_PAY&directSelfPay=1'):
        response = client.get(url)
        assert response.status_code == 200, url
        assert '尚未建立方案' in response.text, url
        assert '血脂肪檢查' not in response.text, url
        assert '115年臺北市' not in response.text, url
        audit = FormAudit()
        audit.feed(response.text)
        assert (audit.forms, audit.inputs, audit.event_handlers) == (0, 0, 0), url
        assert all('site-config' not in str(script) for script in audit.scripts)
        assert 'form-action \'none\'' in response.headers['content-security-policy']


def test_old_shared_price_api_blocked_in_new_8006_but_shanlin_source_works():
    for url in ('/api/self_pay/categories', '/api/self_pay/catalog',
                '/api/self_pay/select', '/api/integrated/catalog/source',
                '/api/integrated/catalog/source?clinic=yidian',
                '/api/self_pay/categories?clinic=shanlin'):
        assert client.get(url).status_code == 423, url
    assert client.post('/api/self_pay/select', json={'item_id': 'I001'}).status_code == 423
    source = client.get('/api/integrated/clinics/shanlin/catalog-source-preview')
    assert source.status_code == 200
    assert source.json()['clinicId'] == 'shanlin'
    assert source.json()['billableUnitCount'] == 56


def test_demo_catalog_profile_is_not_a_shanlin_price_alias():
    yi = client.get('/api/integrated/clinics/yidian/public').json()
    sh = client.get('/api/integrated/clinics/shanlin/public').json()
    assert yi['catalogSource'] == 'not_configured'
    assert yi['sourceCatalogAvailable'] is False
    assert yi['independentDemoCatalogReady'] is False
    assert sh['sourceCatalogAvailable'] is True
    assert sh['catalogSource'] == 'shanlin_existing_source_json'
    assert client.get('/api/integrated/clinics/yidian/catalog-source-preview').status_code == 404


def test_phase7_isolated_app_does_not_change_older_voice_test_app():
    assert app is not voice_stage_app
    assert app.router is not voice_stage_app.router
    original = TestClient(voice_stage_app)
    assert 'IntegratedCatalogGuard.checkSelection' in original.get('/appointment2.html').text
    assert original.get('/api/integrated/catalog/source').status_code == 200
    assert '尚未建立方案' not in original.get('/').text
    assert '尚未建立方案' in client.get('/').text


def test_source_lookup_is_never_called_for_empty_yidian(monkeypatch):
    def forbid(*a, **k):
        raise AssertionError('empty demo may not access Shanlin catalog')
    monkeypatch.setattr(routes, 'load_shanlin_catalog', forbid)
    assert client.get('/?clinic=yidian').status_code == 200
    # A read-only, source-dependent Shanlin render would call the patched loader.


def test_unknown_clinic_never_falls_back_to_yidian_or_shanlin():
    assert client.get('/?clinic=unknown').status_code == 404
    assert client.get('/appointment2.html?clinic=unknown').status_code == 404
    assert client.post('/api/booking/confirm?clinic=yidian', json={}).status_code == 423
    assert client.post('/api/booking/confirm?clinic=shanlin', json={}).status_code == 423


def test_malformed_shared_template_causes_safe_503(monkeypatch):
    original = routes.original_home_page().body.decode('utf-8')
    damaged = original.replace('id="scrollspyAppointment"', 'id="anotherId"', 1)
    monkeypatch.setattr(routes, 'original_home_page', lambda: HTMLResponse(damaged))
    assert client.get('/?clinic=yidian').status_code == 503
