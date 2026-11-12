"""Phase 9 acceptance: real Shanlin source / independent Yidian Demo identity."""
import sys
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

SITE = Path(__file__).resolve().parents[1] / 'website'
sys.path.insert(0, str(SITE))

from integrated_app_clinics import app
import integrated_clinic_routes as routes
from integrated_shanlin_home_catalog import (
    ShanlinCatalogUnavailable, load_shanlin_catalog, price_label,
)

client = TestClient(app)


def test_shanlin_source_verified_counts_and_roles():
    response = client.get('/api/integrated/clinics/shanlin/catalog-source-preview')
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['clinicId'] == 'shanlin'
    assert data['sourceItemCount'] == 101
    assert data['packageCount'] == 9
    assert data['individuallyPricedCount'] == 47
    assert data['billableUnitCount'] == 56
    assert data['pricePendingCount'] == 1
    assert data['categoryDifferencesPendingReview'] == 13
    assert len(data['units']) == 56
    assert data['bookingEnabled'] is False
    assert data['publishedForBooking'] is False
    assert data['readOnly'] is True
    assert data['status'] == 'existing_source_preview_not_published'


def test_shanlin_home_displays_real_source_values_and_every_unit_once():
    response = client.get('/?clinic=shanlin')
    assert response.status_code == 200
    html = response.text
    assert '山林診所<br />自費健檢與加購項目' in html
    assert '山林既有檢查套組' in html
    assert '血液檢測' in html
    assert 'NT$270（來源參考價）' in html
    assert '血脂肪檢查' in html
    assert 'NT$800（來源參考價）' in html
    assert 'pkg_P006' in html and '價格待核對（不可計價）' in html
    assert 'NT$0（來源參考價）' not in html
    assert html.count('class="shanlin-unit-row"') == 56
    assert html.count('class="elderly-plan-card"') == 3
    assert html.count('href="#shanlin-catalog-source"') >= 1
    assert '來源分類：' in html
    assert response.headers['cache-control'] == 'no-store'


def test_source_items_are_read_only_not_an_authorized_pilot_publication():
    catalog = load_shanlin_catalog(SITE)
    assert catalog['sourceHash16']
    assert catalog['publishedForBooking'] is False
    p006 = next(u for u in catalog['units'] if u['id'] == 'pkg_P006')
    assert p006['price'] is None
    assert price_label(p006['price']) == '價格待核對（不可計價）'
    p001 = next(u for u in catalog['units'] if u['id'] == 'pkg_P001')
    assert len(p001['components']) == 8
    assert p001['price'] == 270
    assert p001['enabled'] is False and p001['reviewed'] is False


def test_yidian_is_explicit_demo_not_shanlin_authorized_price():
    profile = client.get('/api/integrated/clinics/yidian/public').json()
    shanlin = client.get('/api/integrated/clinics/shanlin/public').json()
    assert profile['role'] == 'demo_template'
    assert shanlin['role'] == 'existing_data_partner'
    assert profile['catalogSource'] == 'not_configured'
    assert shanlin['catalogSource'] == 'shanlin_existing_source_json'
    homepage = client.get('/?clinic=yidian').text
    booking = client.get('/appointment2.html?clinic=yidian&p=SELF_PAY&directSelfPay=1').text
    assert '空白公版' in homepage and '尚未建立方案' in homepage
    assert '空白公版' in booking and '尚未建立方案' in booking
    assert '山林' not in homepage and '山林' not in booking
    assert '腦肺方案' not in homepage and '血脂肪檢查' not in homepage
    assert client.get('/api/integrated/clinics/yidian/catalog-source-preview').status_code == 404


def test_shanlin_home_keeps_patient_inputs_disabled_and_is_local_only():
    page = client.get('/?clinic=shanlin')
    html = page.text
    assert '<form' not in html
    assert '<input' not in html
    assert 'onclick=' not in html
    assert 'connect-src \'none\'' in page.headers['content-security-policy']
    assert 'form-action \'none\'' in page.headers['content-security-policy']
    assert '自費加購項目' in html
    assert 'booking/confirm' not in html
    assert client.post('/api/booking/confirm?clinic=shanlin', json={}).status_code == 423
    assert client.post('/api/booking/confirm?clinic=yidian', json={}).status_code == 423


def test_external_clients_cannot_view_source_catalog():
    class ExternalClientScope:
        def __init__(self, wrapped): self.wrapped = wrapped
        async def __call__(self, scope, receive, send):
            if scope['type'] == 'http':
                scope = {**scope, 'client': ('203.0.113.9', 12345)}
            await self.wrapped(scope, receive, send)
    with TestClient(ExternalClientScope(app)) as remote:
        assert remote.get('/api/integrated/clinics/shanlin/catalog-source-preview').status_code == 403
        assert remote.get('/?clinic=shanlin').status_code == 403


def test_source_price_inconsistency_blocks_homedisplay(monkeypatch):
    import integrated_shanlin_home_catalog as loader
    actual = loader.snapshot_source_catalog
    def changed(site):
        snapshot = actual(site)
        assert snapshot['available']
        snapshot['items'][0]['price'] += 1
        return snapshot
    monkeypatch.setattr(loader, 'snapshot_source_catalog', changed)
    with pytest.raises(ShanlinCatalogUnavailable):
        loader.load_shanlin_catalog(SITE)
    response = client.get('/?clinic=shanlin')
    assert response.status_code == 503
    assert '不一致' in response.json()['detail'] or '不同' in response.json()['detail']


def test_untrusted_source_text_is_html_escaped(monkeypatch):
    actual = routes.load_shanlin_catalog(SITE)
    fake = {**actual, 'units': [dict(unit) for unit in actual['units']]}
    fake['units'][0]['name'] = '<img src=x onerror=alert(1)>'
    monkeypatch.setattr(routes, 'load_shanlin_catalog', lambda site: fake)
    html = client.get('/?clinic=shanlin').text
    assert '&lt;img src=x onerror=alert(1)&gt;' in html
    assert '<img src=x onerror=alert(1)>' not in html
