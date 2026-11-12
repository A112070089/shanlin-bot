#!/usr/bin/env python3
"""Configure the existing isolated 8018 launcher; no database/network operations."""
from pathlib import Path
import datetime
import json
import os
import runpy
import shutil
import tempfile

ROOT = Path(os.environ.get('DOUBTS_PROJECT_ROOT') or Path(__file__).resolve().parent).expanduser()


def main():
    os.umask(0o077)
    starter = ROOT / 'start_doubts.py'
    if not starter.is_file():
        raise SystemExit('找不到 start_doubts.py；請將本檔放在原專案最外層。')
    launcher = runpy.run_path(str(starter))
    if launcher['test_credential']() is None:
        raise SystemExit('缺少 doubts-shanlin-test 的有效服務帳戶檔案；未修改設定。')
    if launcher['service_secret']() is None:
        raise SystemExit('缺少有效的本機 service-secret；未修改設定。')
    if not (ROOT / 'shanlin_booking_stage' / 'booking_api.py').is_file():
        raise SystemExit('缺少 shanlin_booking_stage/booking_api.py；未修改設定。')
    if not launcher['available_exec'](launcher['project_python']()):
        raise SystemExit('找不到專案 .venv/bin/python；未修改設定。')
    config = launcher['CONFIG']
    settings = {}
    if config.exists():
        try:
            settings = json.loads(config.read_text(encoding='utf-8'))
        except (OSError, ValueError, UnicodeError):
            raise SystemExit('既有設定無法讀取；保留原檔，未修改。')
        if not isinstance(settings, dict):
            raise SystemExit('既有設定格式不是 JSON 物件；未修改。')
    current = settings.get('firebase_database_url', '')
    print('只設定 doubts-shanlin-test 的隔離測試服務。')
    print('請從 Firebase Console 的 doubts-shanlin-test 專案 → Realtime Database 複製資料庫網址。')
    print('不要輸入金鑰或山林正式資料庫網址。')
    if isinstance(current, str) and launcher['valid_db_url'](current):
        print('目前網址：' + current)
        prompt = '輸入測試資料庫網址（Enter 沿用目前網址）：'
    else:
        current = ''
        prompt = '輸入測試資料庫網址（空白取消）：'
    try:
        url = input(prompt).strip() or current
    except (EOFError, KeyboardInterrupt):
        raise SystemExit('\n已取消，未修改設定。')
    if not url:
        raise SystemExit('已取消，未修改設定。')
    if not launcher['valid_db_url'](url):
        raise SystemExit('網址未通過 doubts-shanlin-test 測試來源檢查；未修改設定。')
    settings.update(firebase_database_url=url.rstrip('/') + '/', enable_8018_autostart=True)
    config.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if config.exists():
        suffix = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        backup = config.with_name(config.name + '.backup_' + suffix)
        shutil.copy2(config, backup)
        backup.chmod(0o600)
    fd, temporary = tempfile.mkstemp(prefix='.oneclick-local-', dir=config.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(settings, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, config)
    finally:
        Path(temporary).unlink(missing_ok=True)
    print('設定已儲存；尚未連線驗證 Firebase，也尚未啟動 8018。')
    print('請回到終端機執行先前的「只啟動 8018」指令，或使用原本的「啟動 DOUBTS.command」。')


if __name__ == '__main__':
    main()
