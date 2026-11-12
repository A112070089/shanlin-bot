"""In-memory-only self-pay catalog guard for the local integrated 8006 pilot.

Never overwrites appointment2.html or yidian_speech.js. The original booking
and medical-text APIs remain authoritative; the shared contract is a safety
cross-check, not a new source of prices or an automatic catalog publication.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, Response

SITE = Path(__file__).resolve().parent
router = APIRouter()


def _once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError("自費預約頁面版本不符合安全整合條件")
    return text.replace(old, new, 1)


def _within(text: str, begin: str, end: str, edits: tuple[tuple[str, str], ...]) -> str:
    if text.count(begin) != 1 or text.count(end) != 1:
        raise ValueError("找不到唯一的自費預約函式")
    pos_a = text.index(begin)
    pos_b = text.index(end, pos_a + len(begin))
    part = text[pos_a:pos_b]
    for old, new in edits:
        part = _once(part, old, new)
    return text[:pos_a] + part + text[pos_b:]


def make_checked_booking_html(source: str) -> str:
    """Inject validation into only the three existing self-pay read operations.

    Fail closed if any expected anchor changed; never serve a half-instrumented
    integrated page. Original source file is untouched.
    """
    html = _once(source, '  <script>\n\n    "use strict";',
                 '  <script src="/integrated_catalog_guard.js"></script>\n'
                 '  <script>\n\n    "use strict";')
    html = _within(html, '    async function loadSelfPayCategories() {',
                   '    function showSelfPayCategoryButtons() {', (
        ('      try {\n', '      try {\n        await window.IntegratedCatalogGuard.load();\n'),
        ('        selfPayCategories =',
         '        window.IntegratedCatalogGuard.checkCategories(result.categories);\n'
         '        selfPayCategories ='),
    ))
    html = _within(html, '    async function loadSelfPayCategoryItems(',
                   '    async function loadSelfPayItemDetail(', (
        ('      try {\n', '      try {\n        await window.IntegratedCatalogGuard.load();\n'),
        ('        currentSelfPayCategory =',
         '        window.IntegratedCatalogGuard.checkCategoryItems(categoryId, result.items);\n'
         '        currentSelfPayCategory ='),
    ))
    html = _within(html, '    async function loadSelfPayItemDetail(',
                   '    function buildCurrentSelfPaySelection() {', (
        ('      try {\n', '      try {\n        await window.IntegratedCatalogGuard.load();\n'),
        ('        currentSelfPayItem =',
         '        window.IntegratedCatalogGuard.checkSelection(itemId, result);\n'
         '        currentSelfPayItem ='),
    ))
    html = _within(html, '    function addCurrentSelfPayItem() {',
                   '    function showSelectedSelfPayItems() {', (
        ('      if (\n        isSelfPayItemSelected(',
         '      if (selection.price === null || !Number.isSafeInteger(selection.price) || selection.price < 0) {\n'
         '        return { success: false, reason: "price_unconfirmed" };\n'
         '      }\n\n      if (\n        isSelfPayItemSelected('),
    ))
    html = _within(html, '        if (wantsAdd) {',
                   '          /* -------------------------------\n             超過參考預算', (
        ('          /* -------------------------------\n             已經加入過',
         '          if (result.reason === "price_unconfirmed") {\n'
         '            addSelfPayAIMessage("此檢查項目的價格尚未經診所核定，暫時無法加入預約清單，請向診所確認價格。");\n'
         '            selfPayChatMode = "item";\n'
         '            showSelfPayItemButtons();\n'
         '            return;\n'
         '          }\n\n'
         '          /* -------------------------------\n             已經加入過'),
    ))
    return html


@router.get('/appointment2.html', include_in_schema=False)
def checked_booking_page():
    try:
        content = (SITE / 'appointment2.html').read_text(encoding='utf-8')
        html = make_checked_booking_html(content)
    except (OSError, ValueError) as exc:
        raise HTTPException(503, '預約頁面版本待確認，暫停整合測試') from exc
    return HTMLResponse(html, headers={
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
    })


@router.get('/integrated_catalog_guard.js', include_in_schema=False)
def checked_catalog_script():
    try:
        content = (SITE / 'integrated_catalog_guard.js').read_text(encoding='utf-8')
    except OSError as exc:
        raise HTTPException(503, '共用健檢目錄核對程式無法載入') from exc
    return Response(content, media_type='application/javascript', headers={
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
    })
