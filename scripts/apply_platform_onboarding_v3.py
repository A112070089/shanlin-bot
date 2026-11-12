"""Idempotently add V3 draft setup links to the V2.1 clinic center UI.

Modifies only one UI script; backs up prior contents. No secrets or DB touched.
"""
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / 'website' / 'platform_static' / 'clinic-center.js'
BACKUP = ROOT / 'backups' / 'platform_onboarding_v3' / 'clinic-center.js'
ANCHOR = '<button type="button" data-edit="${esc(d.clinicId)}" class="outline">編輯／封存</button>'
NEW = ANCHOR + '<a class="back-link smaller" href="/platform/clinics/${encodeURIComponent(d.clinicId)}/setup">開通準備 →</a>'
OLD_NOTICE = '未建立診所帳號・未連接資料庫・不可預約'
NEW_NOTICE = '正式預約尚未開放；開通準備與驗收請進入設定頁'


def main():
    if not FILE.is_file():
        sys.exit('STOP：找不到 v2 診所管理中心腳本；請先安裝 v2、v2.1')
    src = FILE.read_text(encoding='utf-8')
    if NEW in src and NEW_NOTICE in src:
        print('PASS：v3 開通準備入口已經安裝（無須重複修改）')
        return
    if src.count(ANCHOR) != 1 or src.count(OLD_NOTICE) != 1:
        sys.exit('STOP：目前 v2.1 腳本版本與預期不同，未修改任何檔案')
    if not (ROOT / 'website' / 'integrated_app_platform_v3.py').is_file():
        sys.exit('STOP：請先解壓縮 v3 補丁，未修改任何檔案')
    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    if not BACKUP.exists():
        shutil.copy2(FILE, BACKUP)
    FILE.write_text(src.replace(ANCHOR, NEW, 1).replace(OLD_NOTICE, NEW_NOTICE, 1), encoding='utf-8')
    print('PASS：診所草稿新增「開通準備」入口')
    print('PASS：v2 原腳本備份於', BACKUP.relative_to(ROOT))
    print('說明：未修改 Firebase、帳號或其他診所資料')


if __name__ == '__main__':
    main()
