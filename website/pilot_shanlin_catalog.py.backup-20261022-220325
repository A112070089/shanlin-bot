"""Read-only bridge for the EXISTING Shanlin catalog JSON.

This code never updates the source file, the existing self-pay API, or Firebase.
A preview is not a published pilot catalog. Package components are not
separately billable; a package price must never be copied to each component.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json

from pilot_excel import CATEGORIES, category_guess

MAX_SOURCE_BYTES = 5 * 1024 * 1024


def _text(value, max_len=150):
    return str(value or '').strip()[:max_len]


def _price(value):
    return value if type(value) is int and 0 <= value <= 10_000_000 else None


def snapshot_source_catalog(site_dir: Path) -> dict:
    """Read the fixed source path used by the original self_pay_api.py.

    Never accept a source path from HTTP request parameters (SSRF/path access).
    """
    path = Path(site_dir) / '自費項目對話資料庫.json'
    if not path.is_file():
        return {'available': False, 'reason': '原網站資料檔「website/自費項目對話資料庫.json」不存在；請確認原自費項目 API 使用的實際資料來源。',
                'items': [], 'sourceFilename': path.name, 'count': 0, 'packages': 0}
    if path.stat().st_size > MAX_SOURCE_BYTES:
        return {'available': False, 'reason': '原網站健檢資料檔超過安全上限，未進行讀取。',
                'items': [], 'sourceFilename': path.name, 'count': 0, 'packages': 0}
    try:
        raw = path.read_bytes()
        parsed = json.loads(raw.decode('utf-8'))
    except (OSError, ValueError, UnicodeDecodeError):
        return {'available': False, 'reason': '原網站健檢資料檔無法解析，未進行任何修改。',
                'items': [], 'sourceFilename': path.name, 'count': 0, 'packages': 0}
    if not isinstance(parsed, dict) or not isinstance(parsed.get('items'), list) or not isinstance(parsed.get('packages'), list):
        return {'available': False, 'reason': '原網站健檢資料不是預期格式，需要檢查 self_pay_api.py 的來源設定。',
                'items': [], 'sourceFilename': path.name, 'count': 0, 'packages': 0}
    item_map = {str(x.get('id')): x for x in parsed['items'] if isinstance(x, dict) and x.get('id')}
    results, seen = [], set()
    for package in parsed['packages'][:500]:
        if not isinstance(package, dict):
            continue
        original_id = _text(package.get('package_id'), 32)
        if not original_id or ('pkg_' + original_id) in seen:
            continue
        name = _text(package.get('name'))
        if not name:
            continue
        components = []
        for inner_id in (package.get('items') or [])[:100]:
            component = item_map.get(str(inner_id))
            if component and component.get('name'):
                components.append({'name': _text(component['name']), 'meaning': _text(component.get('plain_explanation'), 1000)})
        price = _price(package.get('price'))
        results.append({
            'id': 'pkg_' + original_id,
            'name': name,
            'categoryId': category_guess(_text(package.get('category')), name),
            'type': 'package', 'description': _text(package.get('plain_explanation'), 4000),
            'price': price, 'components': components, 'reviewed': False, 'enabled': False,
            'originalGroup': _text(package.get('category')), 'sourceSheet': _text(package.get('sheet')),
            'sourceRows': '', 'issue': '來源價格無效，需人工核對' if price is None else '',
        })
        seen.add('pkg_' + original_id)
    for item in parsed['items'][:1500]:
        if not isinstance(item, dict):
            continue
        # DO NOT include per-component prices: they often repeat the PACKAGE total.
        if item.get('price_type') != 'individual':
            continue
        original_id = _text(item.get('id'), 32)
        name = _text(item.get('name'))
        if not original_id or not name or ('item_' + original_id) in seen:
            continue
        price = _price(item.get('price'))
        results.append({
            'id': 'item_' + original_id, 'name': name,
            'categoryId': category_guess(_text(item.get('category')), name),
            'type': 'single', 'description': _text(item.get('plain_explanation') or item.get('clinical_reference'), 4000),
            'price': price, 'components': [], 'reviewed': False, 'enabled': False,
            'originalGroup': _text(item.get('category')), 'sourceSheet': _text(item.get('sheet')),
            'sourceRows': _text(item.get('source_row'), 30),
            'issue': '來源價格無效，需人工核對' if price is None else '',
        })
        seen.add('item_' + original_id)
    if not results:
        return {'available': False, 'reason': '原網站檔案可讀取，但沒有可確認的套組或獨立計價項目。',
                'items': [], 'sourceFilename': path.name, 'count': 0, 'packages': 0}
    return {
        'available': True, 'reason': '來源為原網站檔案的即時讀取快照，不代表已發布至公版或寫回原預約網站。',
        'sourceFilename': path.name,
        'sourceHash': sha256(raw).hexdigest()[:16],
        'sourceModifiedAt': datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec='seconds'),
        'count': len(results), 'packages': sum(x['type'] == 'package' for x in results),
        'categories': CATEGORIES, 'items': results,
        'schemaVersion': 'clinic-catalog/v1',
    }
