"""An additive, read-only catalog contract shared by future booking/voice clients.

Only the EXISTING original booking JSON and existing self_pay_api runtime are
consulted. No preview drafts, unpublished pilot rows, patient details, Firebase,
or pricing overrides ever enter this contract. This module DOES NOT switch the
current booking or speech routes to a new data source.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from integrated_catalog_validation import reconcile
from integrated_release_validation import load_source


class SharedCatalogUnavailable(Exception):
    """Fail closed when original booking runtime and its source disagree."""


def _sensible_price(value: Any) -> bool:
    return type(value) is int and 0 <= value <= 10_000_000


def make_shared_catalog(site: Path | None = None) -> dict[str, Any]:
    """Return an explicitly unapproved, immutable-in-use public catalog view.

    Original booking is still authoritative. Failing reconciliation means the
    server should stop serving this bridge rather than silently using stale
    price or membership data. Caller must not persist or publish the result.
    """
    site = Path(site or Path(__file__).resolve().parent)
    report = reconcile(site)
    if not report.get('priceOrStructureConsistent'):
        raise SharedCatalogUnavailable('原網站計價資料與執行中版本不一致，停止共用目錄')

    raw, source_hash = load_source(site)
    if report.get('sourceHash16') != source_hash:
        raise SharedCatalogUnavailable('原網站目錄版本在驗證期間改變')

    # Import the actual in-memory objects used by the original booking API,
    # rather than silently parsing a separate unverified pricing copy.
    from self_pay_api import ITEM_BY_ID, PACKAGES, billable_from_item

    items_by_id = {i['id']: i for i in raw['items']}
    units: list[dict[str, Any]] = []
    for item in raw['items']:
        if item.get('price_type') != 'individual':
            continue
        runtime = ITEM_BY_ID[item['id']]
        charge = billable_from_item(runtime)
        if charge.get('key') != 'item:' + item['id'] or charge.get('price') != item.get('price'):
            raise SharedCatalogUnavailable('單項費用與原預約 API 不一致')
        price = charge['price']
        units.append({
            'id': 'item_' + item['id'],
            'originalId': item['id'],
            'type': 'single',
            'name': runtime['name'],
            'categoryId': runtime.get('category_id'),
            'price': price if _sensible_price(price) else None,
            'priceConfirmedBySource': _sensible_price(price),
            'memberIds': [],
        })

    for package in raw['packages']:
        package_id = package['package_id']
        runtime = PACKAGES[package_id]
        if runtime.get('price') != package.get('price') or runtime.get('items') != package.get('items'):
            raise SharedCatalogUnavailable('套組計價或成員與原預約 API 不一致')
        price = runtime.get('price')
        units.append({
            'id': 'pkg_' + package_id,
            'originalId': package_id,
            'type': 'package',
            'name': runtime['name'],
            'categoryId': runtime.get('category_id'),
            'price': price if _sensible_price(price) else None,
            'priceConfirmedBySource': _sensible_price(price),
            'memberIds': list(runtime['items']),
        })

    unit_by_id = {unit['id']: unit for unit in units}
    if len(unit_by_id) != len(units) or len(unit_by_id) != report['billableUnitCount']:
        raise SharedCatalogUnavailable('計價單位有重複或數量不一致')

    explanations: list[dict[str, Any]] = []
    for item in raw['items']:
        original_id = item['id']
        runtime = ITEM_BY_ID[original_id]
        charge = billable_from_item(runtime)
        unit_id = ('pkg_' + item['package_id'] if item.get('price_type') == 'package_component'
                   else 'item_' + original_id)
        unit = unit_by_id.get(unit_id)
        if unit is None:
            raise SharedCatalogUnavailable('檢查細項找不到對應計價單位')
        if charge.get('price') != unit['price']:
            raise SharedCatalogUnavailable('檢查細項與其套組的實際計價不一致')
        explanations.append({
            'id': original_id,
            'name': runtime['name'],
            'billableId': unit_id,
            'isPackageComponent': item.get('price_type') == 'package_component',
            # No component price. Original JSON repeats PACKAGE price on members.
            'categoryId': runtime.get('category_id'),
        })

    return {
        'contractVersion': 'shared-catalog-preview/v1',
        'source': 'original_booking_json',
        'sourceHash16': source_hash,
        'readOnly': True,
        'publishedPilotActive': False,
        'bookingSourceSwitched': False,
        'voiceSourceSwitched': False,
        'clinicalReviewCompleted': False,
        'itemCount': len(explanations),
        'packageCount': len(raw['packages']),
        'unitCount': len(units),
        'pricePendingCount': sum(u['price'] is None for u in units),
        'categoryDifferencesPendingReview': report['categoryDifferenceCount'],
        'units': units,
        'items': explanations,
    }
