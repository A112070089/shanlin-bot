#!/usr/bin/env python3
"""Modify ONLY the rendered homepage wording for both clinic identities.

Keeps original website/index.html and all routing, booking, speech logic intact.
Target integration: integrated_app_home_restored:app (port 8006).
"""
from __future__ import annotations

import ast
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'website' / 'integrated_home_restore.py'
BACKUP = ROOT / 'backups' / 'home_labels_before' / 'integrated_home_restore.py'


def replace_exact(text: str, old: str, new: str, label: str) -> str:
    found = text.count(old)
    if found != 1:
        raise SystemExit(f'STOP: {label} position expected once, found {found}; no files changed.')
    return text.replace(old, new, 1)


def main() -> None:
    if not TARGET.is_file():
        raise SystemExit('STOP: Cannot find website/integrated_home_restore.py; no files changed.')
    source = TARGET.read_text(encoding='utf-8')
    if 'def _update_shared_home_labels(html: str) -> str:' in source:
        if source.count('_update_shared_home_labels(html)') == 2:
            print('PASS: Both homepages already use the updated labels. No changes needed.')
            return
        raise SystemExit('STOP: Detected a partial previous edit; no files changed.')

    helper = '''def _update_shared_home_labels(html: str) -> str:
    """Three text-only updates shared by Yidian and Shanlin homepages."""
    old_title = '115年臺北市<br />老人健康檢查'
    new_title = '健康檢查<br />預約服務'
    if old_title in html:
        html = once(html, old_title, new_title, '共用主標題')
    elif new_title not in html:
        raise HTTPException(503, '首頁標題不是預期版本，已停止替換')
    for old, new in (
        ('老人健檢語音助理', '高齡健檢語音助理'),
        ('自費加購語音助理', '自費健檢語音助理'),
    ):
        if old not in html:
            raise HTTPException(503, '原首頁語音助理按鈕不存在，已停止替換')
        html = html.replace(old, new)
    return html


'''
    s = replace_exact(source,
        'def replace_region(text: str, start: str, stop: str, replacement: str, label: str) -> str:',
        helper + 'def replace_region(text: str, start: str, stop: str, replacement: str, label: str) -> str:',
        'insert shared text-only helper')

    start_sh = s.index('def build_shanlin_home() -> HTMLResponse:')
    end_sh = s.index('EMPTY_CARDS =', start_sh)
    block = s[start_sh:end_sh]
    block = replace_exact(block,
        "return HTMLResponse(html, headers={**HEADERS, 'X-Clinic-Id': 'shanlin'})",
        "return HTMLResponse(_update_shared_home_labels(html), headers={**HEADERS, 'X-Clinic-Id': 'shanlin'})",
        'Shanlin homepage response')
    s = s[:start_sh] + block + s[end_sh:]

    start_yi = s.index('def build_yidian_home() -> HTMLResponse:')
    end_yi = s.index('def scoped_booking_preview(', start_yi)
    block = s[start_yi:end_yi]
    block = replace_exact(block,
        "return HTMLResponse(html, headers={**HEADERS, 'X-Clinic-Id': 'yidian',",
        "return HTMLResponse(_update_shared_home_labels(html), headers={**HEADERS, 'X-Clinic-Id': 'yidian',",
        'Yidian homepage response')
    s = s[:start_yi] + block + s[end_yi:]

    ast.parse(s, filename=str(TARGET))
    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    if not BACKUP.exists():
        shutil.copy2(TARGET, BACKUP)
    temp = TARGET.with_name(TARGET.name + '.home-labels-new')
    temp.write_text(s, encoding='utf-8')
    temp.replace(TARGET)
    print('PASS: Updated BOTH Yidian and Shanlin homepages with the three requested labels.')
    print('PASS: No changes to original index.html, CSS, JS, booking, prices, or Firebase.')
    print('Backup:', BACKUP.relative_to(ROOT))


if __name__ == '__main__':
    main()
