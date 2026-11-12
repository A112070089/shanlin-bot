"""Regression contract tests, using only the existing original mock site data.

Tests read original source and in-memory self_pay_api; no Firebase, booking
submissions, pilot publishing, or change to the original JSON is performed.
"""
import sys
from pathlib import Path

from fastapi.testclient import TestClient

SITE = Path(__file__).resolve().parents[1] / 'website'
sys.path.insert(0, str(SITE))

from integrated_shared_catalog import SharedCatalogUnavailable, make_shared_catalog
from integrated_app_shared import app
from self_pay_api import ITEM_BY_ID, billable_from_item


def test_contract_counts_and_source_pinning():
    data = make_shared_catalog()
    assert (data['itemCount'], data['packageCount'], data['unitCount']) == (101, 9, 56)
    assert data['source'] == 'original_booking_json'
    assert data['contractVersion'] == 'shared-catalog-preview/v1'
    assert len(data['sourceHash16']) == 16


def test_unpriced_package_is_explicit_not_guessed():
    data = make_shared_catalog()
    unit = next(x for x in data['units'] if x['id'] == 'pkg_P006')
    assert unit['price'] is None
    assert unit['priceConfirmedBySource'] is False
    assert data['pricePendingCount'] == 1


def test_101_explanations_reference_single_billing_unit():
    data = make_shared_catalog()
    units = {x['id']: x for x in data['units']}
    assert len(units) == 56
    for item in data['items']:
        assert item['billableId'] in units
        original = ITEM_BY_ID[item['id']]
        charge = billable_from_item(original)
        assert units[item['billableId']]['price'] == charge['price']
    assert sum(x['isPackageComponent'] for x in data['items']) == 54


def test_no_repeated_package_prices_in_component_records():
    data = make_shared_catalog()
    assert all('price' not in x for x in data['items'])
    assert any(x['isPackageComponent'] and x['billableId'] == 'pkg_P001' for x in data['items'])


def test_explicitly_no_runtime_source_switch_or_publication():
    data = make_shared_catalog()
    assert data['readOnly'] is True
    assert data['publishedPilotActive'] is False
    assert data['bookingSourceSwitched'] is False
    assert data['voiceSourceSwitched'] is False
    assert data['clinicalReviewCompleted'] is False
    assert data['categoryDifferencesPendingReview'] == 13


def test_mismatch_fails_closed(monkeypatch):
    import integrated_shared_catalog as mod
    monkeypatch.setattr(mod, 'reconcile', lambda site: {'priceOrStructureConsistent': False})
    try:
        make_shared_catalog()
        assert False, 'Expected source mismatch to stop feed'
    except SharedCatalogUnavailable:
        pass


def test_authenticated_pilot_is_not_needed_and_no_db_access(monkeypatch):
    import pilot_backend
    monkeypatch.setattr(pilot_backend, 'store', lambda: (_ for _ in ()).throw(AssertionError('unexpected Firebase or local pilot access')))
    client = TestClient(app)
    response = client.get('/api/integrated/catalog/source')
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    assert response.json()['unitCount'] == 56


def test_route_stops_when_source_inconsistent(monkeypatch):
    import integrated_shared_catalog_routes as mod
    def bad():
        raise SharedCatalogUnavailable('internal fixture error')
    monkeypatch.setattr(mod, 'make_shared_catalog', bad)
    response = TestClient(app).get('/api/integrated/catalog/source')
    assert response.status_code == 503
    assert 'internal fixture' not in response.text
