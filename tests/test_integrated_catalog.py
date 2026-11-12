"""Read-only verification of catalog reconciler against the local source data."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'website'))

from integrated_catalog_validation import reconcile


def test_legacy_and_pilot_are_consistent():
    result = reconcile(ROOT / 'website')
    assert result['priceOrStructureConsistent'], result['blockingIssues']
    assert result['rawItemCount'] == 101
    assert result['packageCount'] == 9
    assert result['packageComponentCount'] == 54
    assert result['individuallyPricedCount'] == 47
    assert result['billableUnitCount'] == result['previewCount'] == 56
    assert result['automaticPublishingEnabled'] is False
    assert result['changesWritten'] is False


def test_unpriced_package_flagged_without_fabricating_price():
    result = reconcile(ROOT / 'website')
    assert any(x['id'] == 'P006' and x['name'] == '甲狀腺檢測' for x in result['unpriced'])


def test_category_differences_are_disclosed_not_silently_overwritten():
    result = reconcile(ROOT / 'website')
    assert result['categoryDifferenceCount'] > 0
    assert result['categoryReviewRequired'] is True
    assert any(x['id'] == 'P002' for x in result['categoryDifferences'])


def test_changed_source_is_detected_without_touching_real_data(tmp_path):
    """Simulate stale booking runtime with a tampered TEMPORARY source JSON."""
    import json
    source = ROOT / 'website' / '自費項目對話資料庫.json'
    document = json.loads(source.read_text(encoding='utf-8'))
    one = next(item for item in document['items'] if item['price_type'] == 'individual')
    one['price'] += 1
    (tmp_path / source.name).write_text(json.dumps(document, ensure_ascii=False), encoding='utf-8')

    result = reconcile(tmp_path)
    assert result['priceOrStructureConsistent'] is False
    assert any('原預約 API' in issue for issue in result['blockingIssues'])
    assert result['changesWritten'] is False
