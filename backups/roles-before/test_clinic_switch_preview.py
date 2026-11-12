"""Phase 7 local-only dual clinic identity / tenant isolation (no DB writes)."""
from pathlib import Path
import sys

from fastapi.testclient import TestClient

SITE = Path(__file__).resolve().parents[1] / 'website'
sys.path.insert(0, str(SITE))

from integrated_app_clinics import app
from integrated_clinic_routes import preview_config

client = TestClient(app)


def test_chooser_shows_two_distinct_clinic_links_and_warning():
    r = client.get('/clinics')
    assert r.status_code == 200
    assert '頤典診所' in r.text and '山林診所' in r.text
    assert 'clinic=yidian' in r.text and 'clinic=shanlin' in r.text
    assert '正式預約' in r.text
    assert '<form' not in r.text
    assert r.headers['cache-control'] == 'no-store'


def test_yidian_preview_retains_selfpay_and_taigi_instrumentation():
    r = client.get('/appointment2.html?clinic=yidian&p=SELF_PAY&directSelfPay=1')
    assert r.status_code == 200
    assert 'IntegratedCatalogGuard.checkSelection' in r.text
    assert 'src="yidian_speech.js"' in r.text
    assert 'data-clinic="name">頤典診所' in r.text
    assert 'id="integrated-clinic-warning"' in r.text
    assert '不能送出正式預約' in r.text
    assert 'integrated-clinic-identity' in r.text
    assert r.headers['cache-control'] == 'no-store'


def test_shanlin_is_read_only_and_contains_no_booking_form_or_old_brand():
    for url in (
        '/appointment2.html?clinic=shanlin&p=SELF_PAY&directSelfPay=1',
        '/index.html?clinic=shanlin',
        '/clinics/shanlin',
    ):
        r = client.get(url)
        assert r.status_code == 200, url
        assert '<h1 class="display-3 fw-bolder mb-3">山林診所<br />健康檢查服務</h1>' in r.text
        assert '尚未開放預約' in r.text
        assert '<form' not in r.text
        assert 'name="pid"' not in r.text
        assert '/api/booking/confirm' not in r.text
        assert 'self_pay_api' not in r.text
        assert 'yidian_speech.js' not in r.text
        assert '407號' not in r.text
        assert '/pilot?clinic=shanlin' in r.text


def test_unknown_clinic_rejected_instead_of_falling_back_to_yidian():
    for url in (
        '/appointment2.html?clinic=unknown',
        '/index.html?clinic=unknown',
        '/clinics/unknown',
        '/api/integrated/clinics/unknown/public',
        '/api/clinic-config?clinic=unknown',
    ):
        assert client.get(url).status_code in (404, 423), url


def test_profiles_are_explicitly_unverified_and_not_real_booking():
    r = client.get('/api/integrated/clinics')
    assert r.status_code == 200
    c = r.json()['clinics']
    assert [x['clinicId'] for x in c] == ['yidian', 'shanlin']
    assert [x['name'] for x in c] == ['頤典診所', '山林診所']
    assert all(x['backendIsolationVerified'] is False and x['bookingEnabled'] is False for x in c)
    public = client.get('/api/integrated/clinics/shanlin/public').json()
    assert public['name'] == '山林診所' and public['verifiedScheduleAvailable'] is False
    assert 'phone' not in public and 'address' not in public


def test_no_legacy_firebase_reads_for_preview_identity_slots_and_questions(monkeypatch):
    import main
    def forbid(*_args, **_kwargs):
        raise AssertionError('must not read legacy Firebase booking config')
    monkeypatch.setattr(main, 'init_firebase', forbid)
    config = client.get('/api/clinic-config').json()
    assert config['clinic']['name'] == '頤典診所'
    assert config['previewOnly'] is True
    assert config['clinic']['elderlyDates'] == []
    assert all(not times for times in config['clinic']['selfPayWeekly'].values())
    assert config['clinic']['phone'] == ''
    available = client.get('/api/availability').json()
    assert available['elderly'] == {} and available['selfPay'] == {}
    questions = client.get('/api/questions?mode=self_pay').json()
    assert questions['questions'] == [] and questions['previewOnly'] is True
    assert preview_config()['name'] == '頤典診所'


def test_booking_confirmation_is_always_locked_before_original_handler(monkeypatch):
    import main
    monkeypatch.setattr(main, 'init_firebase', lambda: (_ for _ in ()).throw(AssertionError('wrote firebase')))
    for endpoint in ('/api/booking/confirm', '/api/booking/confirm?clinic=yidian',
                     '/api/booking/confirm?clinic=shanlin'):
        r = client.post(endpoint, json={'name':'NotReal','pid':'A123456789'})
        assert r.status_code == 423, endpoint
        assert '不接受正式預約' in r.json()['detail']


def test_shanlin_cannot_read_original_booking_catalog_or_legacy_config():
    for url in (
        '/api/self_pay/categories?clinic=shanlin',
        '/api/integrated/catalog/source?clinic=shanlin',
        '/api/availability?clinic=shanlin',
        '/api/questions?clinic=shanlin',
        '/api/clinic-config?clinic=shanlin',
    ):
        assert client.get(url).status_code == 423, url
    assert client.get('/api/self_pay/categories').status_code == 200


def test_original_home_and_source_remain_available_unchanged():
    root = client.get('/')
    assert root.status_code == 200
    assert 'const api=String(window.SITE?.bookingApi || location.origin)' in root.text
    assert 'id="integrated-clinic-home-notice"' in root.text
    assert 'appointment2.html?clinic=yidian&p=SELF_PAY&directSelfPay=1' in root.text
    assert 'clinicId: "yidian"' in root.text
    assert '切換診所' not in root.text
    original = (SITE / 'appointment2.html').read_text(encoding='utf-8')
    assert 'integrated-clinic-warning' not in original
    assert 'integrated-clinic-identity' not in original
    assert client.get('/integrated/voice-diagnostics').status_code == 200


def test_new_clinic_pages_are_local_only():
    class ExternalClientScope:
        def __init__(self, wrapped): self.wrapped = wrapped
        async def __call__(self, scope, receive, send):
            if scope['type'] == 'http':
                scope = {**scope, 'client': ('203.0.113.9', 12345)}
            await self.wrapped(scope, receive, send)
    with TestClient(ExternalClientScope(app)) as remote:
        assert remote.get('/clinics').status_code == 403
        assert remote.get('/appointment2.html?clinic=shanlin').status_code == 403
        assert remote.get('/api/integrated/clinics').status_code == 403


def test_choose_clinic_only_at_home_not_at_form():
    hub = client.get('/clinics')
    assert hub.status_code == 200
    assert '/?clinic=yidian' in hub.text
    assert '/?clinic=shanlin' in hub.text
    assert 'href="/appointment2.html?clinic=' not in hub.text

    start_yidian = client.get('/clinics/yidian')
    assert start_yidian.status_code == 200
    assert start_yidian.url.path == '/'
    assert start_yidian.url.query.decode('ascii') == 'clinic=yidian'
    assert 'appointment2.html?clinic=yidian&p=SELF_PAY&directSelfPay=1' in start_yidian.text
    assert '切換診所' not in start_yidian.text

    start_shanlin = client.get('/clinics/shanlin')
    assert start_shanlin.status_code == 200
    assert start_shanlin.url.path == '/'
    assert start_shanlin.url.query.decode('ascii') == 'clinic=shanlin'
    assert '<h1 class="display-3 fw-bolder mb-3">山林診所<br />健康檢查服務</h1>' in start_shanlin.text
    assert '<span data-clinic="name">山林診所</span>' in start_shanlin.text
    assert '<span data-clinic="name">頤典診所</span>' not in start_shanlin.text
    assert 'src="yidian_speech.js"' not in start_shanlin.text
    assert '<form' not in start_shanlin.text


def test_home_handoff_protects_original_source_files():
    homepage = (SITE / 'index.html').read_text(encoding='utf-8')
    booking = (SITE / 'appointment2.html').read_text(encoding='utf-8')
    assert '"appointment2.html?p=SELF_PAY&directSelfPay=1";' in homepage
    assert '"appointment2.html?clinic=yidian' not in homepage
    assert 'integrated-clinic-home-notice' not in homepage
    assert 'integrated-clinic-warning' not in booking
    assert 'integrated-clinic-identity' not in booking
    assert '切換診所' not in client.get('/appointment2.html?clinic=yidian').text
