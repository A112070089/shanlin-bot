"""Read-only local check of currently available published catalog mapping.

Uses configured pilot storage. May read Firebase if configured; NEVER writes.
Run from project root: ./.venv/bin/python scripts/check_catalog_release.py
"""
from pathlib import Path
import sys

SITE = Path(__file__).resolve().parents[1] / 'website'
sys.path.insert(0, str(SITE))

from integrated_release_validation import load_source, preview_published_release
from pilot_backend import clinic_storage_mode, store


def main():
    source, source_hash = load_source(SITE)
    mode = clinic_storage_mode('shanlin')
    print('=== 健檢目錄發布前對應檢查（唯讀）===')
    print('儲存模式：', mode)
    published = store().read('shanlin', 'catalog_published')
    report = preview_published_release(source, published, source_hash)
    print('原網站版本指紋：', report['sourceHash16'])
    print('公版發布版本：', report['publishedVersion'] or '尚未發布')
    print('已啟用的公版項目：', report['publishedCount'])
    print('可正確對應原網站的項目：', report['mappedEnabledCount'])
    print('價格差異：', len(report['priceChanges']))
    print('分類差異：', len(report['categoryDifferences']))
    for issue in report['issues']:
        print('BLOCK：', issue)
    for warning in report['warnings']:
        print('REVIEW：', warning)
    print('是否實際切換預約資料來源：否')
    print('是否修改 Firebase／JSON：否')
    print('RESULT：唯讀發布對應檢查完成')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print('STOP：無法讀取公版資料或來源檔案')
        print('錯誤類型：', type(exc).__name__)
        raise SystemExit(1)
