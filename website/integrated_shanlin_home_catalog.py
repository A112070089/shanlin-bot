"""Validated, read-only Shanlin catalog view for the LOCAL shared homepage.

The source is the existing clinic JSON, NOT a public pilot publication.
No patient data, Firebase reads/writes, appointment writes, or guessed prices.
"""
from __future__ import annotations

from collections import defaultdict
from html import escape
from pathlib import Path

from integrated_shared_catalog import SharedCatalogUnavailable, make_shared_catalog
from pilot_shanlin_catalog import snapshot_source_catalog


class ShanlinCatalogUnavailable(Exception):
    """Stop the entire clinic view if runtime/source prices diverge."""


def load_shanlin_catalog(site: Path) -> dict:
    """Reconcile source JSON, original booking runtime, and original preview.

    Kept separate from public ``pilot/catalog_published``: original source exists
    but this does NOT imply administrative review or publication.
    """
    snapshot = snapshot_source_catalog(site)
    if not snapshot.get('available'):
        raise ShanlinCatalogUnavailable('山林既有健檢目錄無法讀取，停止展示')
    try:
        contract = make_shared_catalog(site)
    except (SharedCatalogUnavailable, OSError, ValueError, KeyError, TypeError) as exc:
        raise ShanlinCatalogUnavailable('山林來源目錄與原預約計價版本不一致，停止展示') from exc
    if snapshot.get('sourceHash') != contract.get('sourceHash16'):
        raise ShanlinCatalogUnavailable('山林來源目錄在讀取期間已改變，停止展示')
    expected = {row['id']: row for row in contract['units']}
    actual = {row['id']: row for row in snapshot['items']}
    if (len(expected) != len(contract['units']) or len(actual) != len(snapshot['items'])
            or expected.keys() != actual.keys()):
        raise ShanlinCatalogUnavailable('山林目錄計價單位無法完整對應，停止展示')
    for key, row in actual.items():
        checked = expected[key]
        if (row['name'] != checked['name'] or row['type'] != checked['type']
                or row['price'] != checked['price']):
            raise ShanlinCatalogUnavailable('山林目錄名稱或價格與原預約版本不同，停止展示')
        if row['type'] == 'package' and len(row.get('components') or []) != len(checked['memberIds']):
            raise ShanlinCatalogUnavailable('山林套組成員不一致，停止展示')
    if len(contract['items']) != contract['itemCount']:
        raise ShanlinCatalogUnavailable('山林解說細項缺漏，停止展示')
    return {
        'clinicId': 'shanlin', 'name': '山林診所',
        'status': 'existing_source_preview_not_published',
        'readOnly': True, 'bookingEnabled': False, 'publishedForBooking': False,
        'sourceHash16': snapshot['sourceHash'],
        'sourceItemCount': contract['itemCount'],
        'packageCount': contract['packageCount'],
        'individuallyPricedCount': contract['unitCount'] - contract['packageCount'],
        'billableUnitCount': contract['unitCount'],
        'pricePendingCount': contract['pricePendingCount'],
        'categoryDifferencesPendingReview': contract['categoryDifferencesPendingReview'],
        'units': snapshot['items'],
    }


def price_label(value) -> str:
    if type(value) is int and 0 <= value <= 10_000_000:
        return f'NT${value:,}（來源參考價）'
    return '價格待核對（不可計價）'


def package_card(item: dict, position: int) -> str:
    ident = escape(item['id'], quote=True)
    name = escape(item['name'])
    components = list(item.get('components') or [])
    top = components[:3]
    preview = ''.join(f'<li>{escape(part["name"])}</li>' for part in top)
    full = ''.join(f'<li>{escape(part["name"])}</li>' for part in components)
    card_id = f'shanlinPackage{position}'
    return f'''<article class="elderly-plan-card" aria-labelledby="{card_id}">
      <div class="elderly-plan-header"><span class="elderly-plan-code">{ident}</span>
      <h3 id="{card_id}">{name}</h3></div>
      <p class="elderly-plan-preview-label">{escape(price_label(item['price']))}</p>
      <ul class="elderly-plan-preview">{preview}</ul>
      <details class="elderly-plan-details"><summary>查看套組所含檢查（{len(components)} 項）</summary>
      <ul class="elderly-plan-full-list">{full}</ul></details>
      <span class="elderly-plan-action" aria-disabled="true">僅供瀏覽，尚未開放預約</span>
    </article>'''


def catalog_section(catalog: dict) -> str:
    """Render all units, grouped by original source category (not guess rules)."""
    units = catalog['units']
    package = [row for row in units if row['type'] == 'package']
    singles = [row for row in units if row['type'] == 'single']

    def row_html(item):
        name = escape(item['name'])
        ident = escape(item['id'])
        category = escape(item.get('originalGroup') or '未分類')
        price = escape(price_label(item.get('price')))
        unit_description = ('套組：包含 ' + str(len(item.get('components') or [])) + ' 個檢查細項'
                            if item['type'] == 'package' else '獨立計價單項')
        extra = ''
        if item['type'] == 'package':
            members = ''.join(f'<li>{escape(c["name"])}</li>' for c in item.get('components') or [])
            extra = (f'<details class="shanlin-unit-members"><summary>查看套組細項</summary>'
                     f'<ul>{members}</ul></details>')
        return (f'<li class="shanlin-unit-row" data-source-id="{ident}">'
                f'<div class="shanlin-unit-line"><strong>{name}</strong><span>{price}</span></div>'
                f'<p>{escape(unit_description)} · 來源分類：{category}</p>{extra}</li>')

    groups = defaultdict(list)
    for item in singles:
        groups[item.get('originalGroup') or '未分類'].append(item)
    single_sections = ''.join(
        '<details class="shanlin-catalog-group"><summary>' + escape(category) +
        '（' + str(len(rows)) + ' 項）</summary><ul>' + ''.join(row_html(item) for item in rows) +
        '</ul></details>'
        for category, rows in groups.items()
    )
    package_rows = ''.join(row_html(item) for item in package)
    return f'''<section id="shanlin-catalog-source" class="elderly-booking-v2 shanlin-catalog-section"
      aria-labelledby="shanlinCatalogTitle">
      <div class="elderly-booking-container">
       <header class="elderly-section-heading"><h2 id="shanlinCatalogTitle">山林現有自費加購項目</h2>
        <p>原始資料已有 {catalog['sourceItemCount']} 個檢查細項、{catalog['packageCount']} 個套組，
        可獨立計價 {catalog['billableUnitCount']} 項（{catalog['individuallyPricedCount']} 個單項＋{catalog['packageCount']} 個套組）。
        下列價格來自現有來源資料，僅供本機核對，並非公版已審核發布之正式報價。</p>
       </header>
       <div class="shanlin-catalog-advisory" role="note">資料已存在，不需重新建立。
       其中 {catalog['pricePendingCount']} 項價格待確認、{catalog['categoryDifferencesPendingReview']} 項分類待核對；
       正式預約仍須先接妥山林獨立後端與醫師時段。</div>
       <div class="shanlin-catalog-columns"><section><h3>健檢套組（{len(package)}）</h3>
          <ul>{package_rows}</ul></section>
        <section><h3>獨立計價檢查（{len(singles)}）</h3>{single_sections}</section>
       </div>
      </div></section>'''
