"""Local-only phase 5 tests: no real bookings or Firebase changes."""
import sys
from pathlib import Path

from fastapi.testclient import TestClient

SITE = Path(__file__).resolve().parents[1] / 'website'
sys.path.insert(0, str(SITE))

from integrated_app_booking import app
from integrated_booking_page import make_checked_booking_html
from integrated_shared_catalog import make_shared_catalog


def test_public_booking_page_contains_checked_catalog_bridge():
    response = TestClient(app).get('/appointment2.html')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    body = response.text
    assert '<script src="/integrated_catalog_guard.js"></script>' in body
    assert 'await window.IntegratedCatalogGuard.load()' in body
    assert 'IntegratedCatalogGuard.checkCategories(result.categories)' in body
    assert 'IntegratedCatalogGuard.checkCategoryItems(categoryId, result.items)' in body
    assert 'IntegratedCatalogGuard.checkSelection(itemId, result)' in body
    assert 'selection.price === null' in body
    assert 'result.reason === "price_unconfirmed"' in body


def test_guard_script_is_served_without_cache_and_checks_actual_prices():
    response = TestClient(app).get('/integrated_catalog_guard.js')
    assert response.status_code == 200
    assert 'javascript' in response.headers['content-type']
    assert response.headers['cache-control'] == 'no-store'
    assert '/api/integrated/catalog/source' in response.text
    assert 'billed.price !== unit.price' in response.text
    assert 'row.price !== unit.price' in response.text


def test_original_appointment_html_is_not_modified():
    original = (SITE / 'appointment2.html').read_text(encoding='utf-8')
    assert 'IntegratedCatalogGuard' not in original
    checked = make_checked_booking_html(original)
    assert checked != original
    assert '<script src="/integrated_catalog_guard.js"></script>' in checked


def test_changed_appointment_code_fails_closed():
    original = (SITE / 'appointment2.html').read_text(encoding='utf-8')
    damaged = original.replace('    async function loadSelfPayCategories() {',
                               '    async function loadSelfPayCategoriesV2() {', 1)
    try:
        make_checked_booking_html(damaged)
    except ValueError:
        pass
    else:
        raise AssertionError('Unrecognized source should stop the integration')


def test_existing_booking_api_unchanged_and_available():
    client = TestClient(app)
    cats = client.get('/api/self_pay/categories')
    assert cats.status_code == 200
    assert len(cats.json()['categories']) == 5
    sample_item = make_shared_catalog()['items'][0]
    resp = client.post('/api/self_pay/select', json={'item_id': sample_item['id']})
    assert resp.status_code == 200
    assert resp.json()['item']['id'] == sample_item['id']


def test_unpriced_package_remains_unpriced():
    client = TestClient(app)
    contract = client.get('/api/integrated/catalog/source').json()
    unit = next(row for row in contract['units'] if row['id'] == 'pkg_P006')
    assert unit['price'] is None
    item_id = next(row['id'] for row in contract['items'] if row['billableId'] == unit['id'])
    response = client.post('/api/self_pay/select', json={'item_id': item_id})
    assert response.status_code == 200
    assert response.json()['billable']['price'] is None


def test_pilot_routes_still_available_without_login():
    client = TestClient(app)
    response = client.get('/pilot?clinic=shanlin&view=admin')
    assert response.status_code == 200
    assert 'text/html' in response.headers['content-type']
    assert client.get('/integrated/health').json()['productionReady'] is False
