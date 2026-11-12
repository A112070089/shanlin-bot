"""Synthetic release mapping tests: no production database, no writes."""
import sys
from copy import deepcopy
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'website'
sys.path.insert(0, str(SITE))

from integrated_release_validation import load_source, preview_published_release
from pilot_shanlin_catalog import snapshot_source_catalog
from integrated_app_release import app

source, h = load_source(SITE)
preview = snapshot_source_catalog(SITE)


def published(items):
    return {'status': 'published', 'publishedVersion': 'vlocal_mock', 'items': items}


def reviewed_items():
    rows = deepcopy(preview['items'])
    for row in rows:
        row['reviewed'] = row['price'] is not None
        row['enabled'] = row['price'] is not None
    return rows


def test_not_yet_published_fails_closed():
    report = preview_published_release(source, {}, h)
    assert not report['readyForTechnicalReview']
    assert not report['approvedForRuntime']
    assert report['publishedCount'] == 0


def test_valid_synthetic_release_maps_55_units_without_writes():
    report = preview_published_release(source, published(reviewed_items()), h)
    assert report['publishedCount'] == 55
    assert report['mappedEnabledCount'] == 55, report['issues']
    assert not report['priceChanges']
    assert len(report['categoryDifferences']) == 13
    assert report['readyForTechnicalReview']
    assert not report['approvedForRuntime']
    assert not report['writesPerformed']
    assert not any(x['originalId'] == 'P006' for x in report['mappedItems'])


def test_unknown_enabled_id_is_blocked():
    rows = reviewed_items()
    row = next(x for x in rows if x['enabled'])
    row['id'] = 'imported_different_id'
    report = preview_published_release(source, published(rows), h)
    assert not report['readyForTechnicalReview']
    assert any('無法對應' in x for x in report['issues'])


def test_price_override_is_blocked_until_approval_and_sync():
    rows = reviewed_items()
    next(x for x in rows if x['enabled'])['price'] += 1
    report = preview_published_release(source, published(rows), h)
    assert not report['readyForTechnicalReview']
    assert len(report['priceChanges']) == 1
    assert not report['approvedForRuntime']


def test_package_membership_tamper_is_blocked():
    rows = reviewed_items()
    package = next(x for x in rows if x['type'] == 'package' and x['enabled'])
    package['components'].pop()
    report = preview_published_release(source, published(rows), h)
    assert not report['readyForTechnicalReview']
    assert any('套組成員' in x for x in report['issues'])


def test_readonly_endpoint_requires_admin_login():
    client = TestClient(app)
    response = client.get('/api/integrated/admin/catalog/release-preview')
    assert response.status_code == 401


def test_preview_endpoint_is_admin_only_and_never_writes(monkeypatch):
    import pilot_backend
    class SafeStore:
        def read(self, clinic, kind):
            assert clinic == 'shanlin' and kind == 'catalog_published'
            return published(reviewed_items())
        def write(self, *a, **kw):
            raise AssertionError('unexpected write')
    monkeypatch.setattr(pilot_backend, 'store', lambda: SafeStore())
    app.dependency_overrides[pilot_backend.require_clinic] = lambda: {'clinic': 'shanlin'}
    try:
        client = TestClient(app)
        response = client.get('/api/integrated/admin/catalog/release-preview')
        assert response.status_code == 200, response.text
        assert response.headers['cache-control'] == 'no-store'
        data = response.json()
        assert data['mappedEnabledCount'] == 55
        assert data['approvedForRuntime'] is False
    finally:
        app.dependency_overrides.pop(pilot_backend.require_clinic, None)
