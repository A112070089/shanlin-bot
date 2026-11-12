"""UI contract for restoring exact homepage composition without cross-clinic bookings."""
from pathlib import Path
import sys

from fastapi.testclient import TestClient

SITE = Path(__file__).resolve().parents[1] / 'website'
sys.path.insert(0, str(SITE))
from integrated_app_home_restored import app

client = TestClient(app)


def page(clinic):
    r = client.get('/?clinic=' + clinic)
    assert r.status_code == 200, (clinic, r.status_code, r.text[:500])
    return r.text


def test_same_source_styles_and_unchanged_nav_skeleton():
    yi, sh = page('yidian'), page('shanlin')
    for css in ('./assets/css/index.css?v=doubts-ui-v4', 'elderly-home-hero-v2',
                'elderly-booking-v2', 'senior-hero-actions-v14', 'elderly-plan-grid',
                'footer', 'id="scrollspyFooter"'):
        assert css in yi, css
        assert css in sh, css
    for t in ('首頁', '預約健檢', '自費項目', '聯絡資訊', '登入'):
        assert t in yi and t in sh


def test_no_setup_flow_and_no_catalog_block_added_to_home():
    yi, sh = page('yidian'), page('shanlin')
    for t in ('公版設定流程', '山林現有檢查套組', '山林現有自費加購項目',
              'pkg_P001', 'pkg_P002', 'pkg_P003', 'shanlin-catalog-section',
              'shared-home-notice', '資料待確認', '地址待診所確認'):
        assert t not in yi, t
        assert t not in sh, t
    for html in (yi, sh):
        assert '<h2 id="elderlyBookingTitle">預約健檢</h2>' in html
        assert '<ol class="elderly-booking-steps"' in html
        assert '先預約' in html and '先填表' in html and '當天注意' in html
        assert '<h2 id="elderlyPlansTitle">健檢方案</h2>' in html


def test_shanlin_home_keeps_existing_exact_contact_values():
    sh = page('shanlin')
    assert '臺北市文山區羅斯福路六段407號2樓' in sh
    assert 'tel:+886-2-29332010' in sh
    assert '02 2933 2010' in sh
    assert '<address class="mb-4" data-clinic="address">' in sh


def test_shanlin_keeps_original_elderly_cards_in_original_location():
    sh = page('shanlin')
    assert '<h3 id="elderlyPlanA">腦肺方案</h3>' in sh
    assert '<h3 id="elderlyPlanB">腹部方案</h3>' in sh
    assert '<h3 id="elderlyPlanC">骨密肌力方案</h3>' in sh
    assert 'href="./appointment.html?clinic=shanlin&amp;p=A"' in sh
    assert 'href="./appointment.html?clinic=shanlin&amp;p=B"' in sh
    assert 'href="./appointment.html?clinic=shanlin&amp;p=C"' in sh


def test_shanlin_home_three_actions_are_clickable_and_original_voice_handlers_exist():
    sh = page('shanlin')
    assert 'href="#scrollspyAppointment"' in sh
    assert 'onclick="document.getElementById(\'chat-widget\').classList.add(\'elderly-readable-v15\'); openChat()"' in sh
    assert 'onclick="openSelfPayChat()"' in sh
    assert 'onclick="openSelfPayBrowser(); return false;"' in sh
    assert '<script src="site-config.js"></script>' in sh
    assert 'window.fetch = function' in sh
    assert 'disabled aria-disabled="true"' not in sh


def test_yidian_same_layout_but_no_real_medical_items_and_buttons_are_clickable():
    yi = page('yidian')
    assert '頤典診所' in yi
    assert '<h2 id="elderlyBookingTitle">預約健檢</h2>' in yi
    assert yi.count('data-template-slot=') == 3
    assert '尚未建立方案' in yi
    for item in ('腦肺方案', '腹部方案', '骨密肌力方案',
                 '甲狀腺刺激素', '胸部X光', '血脂肪檢查',
                 '115年臺北市', '臺北市文山區羅斯福路六段407號2樓'):
        assert item not in yi, item
    assert 'href="#scrollspyAppointment"' in yi
    assert 'onclick="showEmptyClinicMessage()"' in yi
    assert 'disabled aria-disabled="true"' not in yi
    assert 'site-config.js' not in yi


def test_legacy_source_files_are_unchanged():
    original = (SITE / 'index.html').read_text(encoding='utf-8')
    assert '115年臺北市' in original
    assert '<h2 id="elderlyBookingTitle">預約健檢</h2>' in original
    assert '<h3 id="elderlyPlanA">腦肺方案</h3>' in original
    assert '臺北市文山區羅斯福路六段407號2樓' in original
    assert 'integrated-home-clinic-scope' not in original


def test_only_shanlin_can_read_source_catalog_and_stateless_selection():
    assert client.get('/api/self_pay/categories?clinic=shanlin').status_code == 200
    assert client.get('/api/self_pay/categories?clinic=yidian').status_code == 423
    assert client.get('/api/self_pay/categories').status_code == 423
    assert client.get('/api/integrated/catalog/source?clinic=shanlin').status_code == 200
    assert client.get('/api/integrated/catalog/source?clinic=yidian').status_code == 423
    r = client.post('/api/self_pay/select?clinic=shanlin', json={'item_id':'I001'})
    assert r.status_code in (200, 404)


def test_booking_submit_locked_for_any_clinic_without_database_write():
    for u in ('/api/booking/confirm', '/api/booking/confirm?clinic=shanlin',
              '/api/booking/confirm?clinic=yidian'):
        assert client.post(u, json={'name':'dummy'}).status_code == 423


def test_preview_clinic_configs_are_distinct_and_preserve_existing_shanlin_contact():
    sh = client.get('/api/clinic-config?clinic=shanlin')
    yi = client.get('/api/clinic-config?clinic=yidian')
    assert sh.status_code == 200 and yi.status_code == 200
    assert sh.json()['clinic']['name'] == '山林診所'
    assert sh.json()['clinic']['address'] == '臺北市文山區羅斯福路六段407號2樓'
    assert yi.json()['clinic']['name'] == '頤典診所'
    assert yi.json()['clinic']['address'] == ''
    assert client.get('/api/clinic-config').status_code == 423
    assert client.get('/api/availability?clinic=shanlin').json()['elderly'] == {}


def test_shanlin_booking_html_is_not_replaced_by_canned_home():
    # appointment2 source is attached; primary appointment.html is missing
    # from the share bundle but exists on the user's Mac.
    res = client.get('/appointment2.html?clinic=shanlin&p=SELF_PAY&directSelfPay=1')
    assert res.status_code == 200, res.text[:500]
    assert 'integrated-home-clinic-scope' in res.text
    assert '本機展示，尚未接受正式預約' in res.text
    assert '填寫基本資料' in res.text
    yi = client.get('/appointment2.html?clinic=yidian&p=SELF_PAY&directSelfPay=1', follow_redirects=False)
    assert yi.status_code == 303
    assert yi.headers['location'].startswith('/?clinic=yidian')
