"""Read-only preparation of a clinic catalog release candidate.

Never publishes, mutates Firebase, modifies the original JSON, or changes the
booking/voice API. Stable original IDs, names, package membership and prices
must be checked before any future opt-in activation.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any

SOURCE_FILENAME = '自費項目對話資料庫.json'
MAX_FILE_BYTES = 5 * 1024 * 1024


def load_source(site_dir: Path) -> tuple[dict[str, Any], str]:
    path = Path(site_dir) / SOURCE_FILENAME
    if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError('原網站健檢資料缺失或超過大小限制')
    raw = path.read_bytes()
    data = json.loads(raw.decode('utf-8'))
    if not isinstance(data, dict) or not isinstance(data.get('items'), list) or not isinstance(data.get('packages'), list):
        raise ValueError('原網站健檢資料格式不符')
    return data, sha256(raw).hexdigest()[:16]


def _valid_price(price: Any) -> bool:
    return type(price) is int and 0 <= price <= 10_000_000


def preview_published_release(source: dict[str, Any], published: dict[str, Any], source_hash: str) -> dict[str, Any]:
    """Build a sanitized read-only admin preview of *published* billable units.

    It does not build a deployable catalog; only a validated mapping proposal.
    A future release must separately handle source pinning, medical approval,
    atomic publish, rollback, selection eligibility and booking/TTS consumers.
    """
    base = {
        'mode': 'read_only_release_mapping',
        'approvedForRuntime': False,
        'writesPerformed': False,
        'originalBookingModified': False,
        'sourceHash16': source_hash,
        'publishedVersion': None,
        'publishedCount': 0,
        'mappedEnabledCount': 0,
        'readyForTechnicalReview': False,
        'issues': [],
        'warnings': [],
        'priceChanges': [],
        'categoryDifferences': [],
        'mappedItems': [],
    }
    if not isinstance(source, dict):
        base['issues'].append('原網站資料格式錯誤')
        return base
    raw_items = source.get('items')
    raw_packages = source.get('packages')
    if not isinstance(raw_items, list) or not isinstance(raw_packages, list):
        base['issues'].append('原網站缺少 items 或 packages')
        return base
    if not isinstance(published, dict) or published.get('status') != 'published':
        base['issues'].append('公版尚無正式發布的健檢目錄，本次不執行資料共用')
        return base
    version = published.get('publishedVersion')
    if not isinstance(version, str) or not version.strip():
        base['issues'].append('公版已發布目錄缺少版本識別碼')
        return base
    base['publishedVersion'] = version

    original: dict[str, tuple[str, dict[str, Any]]] = {}
    for item in raw_items:
        if not isinstance(item, dict) or not isinstance(item.get('id'), str):
            base['issues'].append('原網站檢查項目格式或 ID 錯誤')
            return base
        if item.get('price_type') == 'individual':
            original['item_' + item['id']] = ('single', item)
    member_by_id = {item['id']: item for item in raw_items if isinstance(item, dict) and isinstance(item.get('id'), str)}
    # Recompute the same categories as the original booking API. The raw JSON
    # does NOT store category_id; booking computes it when importing self_pay_api.
    from self_pay_api import detect_category_id
    booking_categories = {item_id: detect_category_id(item)
                          for item_id, item in member_by_id.items()}
    for package in raw_packages:
        if not isinstance(package, dict) or not isinstance(package.get('package_id'), str):
            base['issues'].append('原網站套組格式或 ID 錯誤')
            return base
        original['pkg_' + package['package_id']] = ('package', package)
        member_ids = package.get('items') or []
        if isinstance(member_ids, list) and member_ids:
            first_id = member_ids[0]
            booking_categories['pkg_' + package['package_id']] = booking_categories.get(first_id, 'other_value_added')
        else:
            booking_categories['pkg_' + package['package_id']] = 'other_value_added'
    rows = published.get('items')
    if not isinstance(rows, list):
        base['issues'].append('公版已發布目錄 items 格式錯誤')
        return base
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str):
            base['issues'].append('公版項目 ID 格式錯誤')
            continue
        uid = row['id']
        if uid in seen:
            base['issues'].append(f'公版項目 ID 重複：{uid}')
            continue
        seen.add(uid)
        if row.get('enabled') is not True:
            continue
        base['publishedCount'] += 1
        if row.get('reviewed') is not True:
            base['issues'].append(f'未經人工核對卻被啟用：{uid}')
            continue
        if uid not in original:
            base['issues'].append(f'已啟用的公版 ID 無法對應原網站：{uid}；不可用名稱猜測')
            continue
        kind, original_data = original[uid]
        if row.get('type') != kind:
            base['issues'].append(f'項目類型不一致：{uid}')
            continue
        if row.get('name') != original_data.get('name'):
            base['issues'].append(f'項目名稱不一致：{uid}；需人工確認映射')
            continue
        price = row.get('price')
        if not _valid_price(price):
            base['issues'].append(f'已啟用項目缺乏有效價格：{uid}')
            continue
        original_price = original_data.get('price')
        if price != original_price:
            base['priceChanges'].append({'id': uid, 'name': row['name'],
                                         'original': original_price, 'published': price})
            base['issues'].append(f'發布價格與原預約價格不同：{uid}；需正式核定與版本切換')
            continue
        if kind == 'package':
            members = original_data.get('items')
            if not isinstance(members, list) or any(x not in member_by_id for x in members):
                base['issues'].append(f'原網站套組成員不完整：{uid}')
                continue
            expected_names = [member_by_id[x].get('name') for x in members]
            shown = row.get('components')
            shown_names = [x.get('name') for x in shown] if isinstance(shown, list) and all(isinstance(x, dict) for x in shown) else []
            if shown_names != expected_names:
                base['issues'].append(f'套組成員與原網站不一致：{uid}')
                continue
        booking_category = (booking_categories.get(uid, 'other_value_added')
                            if kind == 'package' else booking_categories.get(original_data['id'], 'other_value_added'))
        base['mappedEnabledCount'] += 1
        base['mappedItems'].append({
            'pilotId': uid,
            'originalId': original_data['package_id'] if kind == 'package' else original_data['id'],
            'type': kind,
            'name': row['name'],
            'price': price,
            'bookingCategory': booking_category,
            'pilotCategory': row.get('categoryId', ''),
        })
        if kind == 'package':
            base['mappedItems'][-1]['packageComponentCount'] = len(original_data['items'])
        if row.get('categoryId') != booking_category:
            base['categoryDifferences'].append({'id': uid, 'name': row['name'],
                'bookingCategory': booking_category, 'pilotCategory': row.get('categoryId', '')})
    if base['publishedCount'] == 0:
        base['issues'].append('公版尚無已啟用項目')
    if base['categoryDifferences']:
        base['warnings'].append('已啟用項目存在分類差異，必須由診所確認；不會自動覆蓋原網站分類')
    if not base['issues']:
        base['warnings'].append('對應檢查通過，但尚未完成醫療審核、原子發布、回復舊版及預約 API 切換')
    base['readyForTechnicalReview'] = not base['issues'] and base['mappedEnabledCount'] > 0
    return base
