#!/usr/bin/env python3
"""Safe local launcher for the unified DOUBTS 8006 app (no production writes).

Use --check first. Runs with the project's existing virtual environment:
  ./.venv/bin/python scripts/run_doubts_8006.py --check
  ./.venv/bin/python scripts/run_doubts_8006.py --port 8020
  ./.venv/bin/python scripts/run_doubts_8006.py --port 8006

Never starts/stops other services, writes Firebase, or modifies project files.
"""
import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import socket
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'website'
API = 'http://127.0.0.1:8018/api/integration/v365/appointments'
PATH = '/api/integration/v365/appointments'
KEY_DIR = Path.home() / '.config' / 'doubts-shanlin-test'
EXPECTED_PROJECT = 'doubts-shanlin-test'


def stop(message):
    raise SystemExit('STOP: ' + message)


def ready():
    required = (
        'website/integrated_app_platform_main.py',
        'website/integrated_app_platform_booking_unified.py',
        'website/platform_shanlin_unified_ui.py',
        'website/platform_shanlin_booking_stage.py',
        'website/shanlin_admin_booking_stage.html',
        'website/database.json',
        'website/自費項目對話資料庫.json',
    )
    for name in required:
        f = ROOT / name
        if not f.is_file():
            stop(f'主專案缺少必要檔案：{name}；不要用精簡 ZIP 直接啟動')
    try:
        db = json.loads((SITE / 'database.json').read_text(encoding='utf-8'))
        catalog = json.loads((SITE / '自費項目對話資料庫.json').read_text(encoding='utf-8'))
    except (OSError, UnicodeError, ValueError):
        stop('主專案 JSON 無法讀取；未啟動')
    if not isinstance(db.get('NAME_DB'), dict) or not isinstance(catalog.get('items'), list):
        stop('主專案資料格式不正確；未啟動')

    for key in ('PILOT_STORAGE', 'PILOT_SHANLIN_STORAGE', 'PILOT_YIDIAN_STORAGE'):
        if os.getenv(key, 'local-demo') != 'local-demo':
            stop(f'{key} 不是 local-demo；這個測試入口不能使用正式 Firebase 模式')

    key = KEY_DIR / 'firebase-service-account.json'
    secret_path = KEY_DIR / 'service-secret'
    if not key.is_file() or not secret_path.is_file():
        stop('缺少獨立測試 Firebase 金鑰或本機 service-secret')
    try:
        info = json.loads(key.read_text(encoding='utf-8'))
        secret = secret_path.read_text(encoding='ascii').strip()
    except (OSError, ValueError, UnicodeError):
        stop('測試金鑰或簽章金鑰無法讀取')
    if info.get('project_id') != EXPECTED_PROJECT or info.get('type') != 'service_account':
        stop('測試 Firebase 身分不符，拒絕啟動')
    if not re.fullmatch(r'[A-Fa-f0-9]{64,}', secret):
        stop('測試服務簽章金鑰格式不正確')

    # Prove that localhost:8018 accepts the SAME shared secret and is returning
    # only Shanlin synthetic data. This is a read-only signed GET.
    stamp = str(int(time.time()))
    nonce = secrets.token_urlsafe(24)
    checksum = hashlib.sha256(b'').hexdigest()
    message = f'GET\n{PATH}\n{stamp}\n{nonce}\n{checksum}'.encode('utf-8')
    signature = hmac.new(secret.encode('ascii'), message, hashlib.sha256).hexdigest()
    req = Request(API, method='GET', headers={
        'X-DOUBTS-Timestamp': stamp, 'X-DOUBTS-Nonce': nonce,
        'X-DOUBTS-Signature': signature, 'Accept': 'application/json',
    })
    try:
        with build_opener(ProxyHandler({})).open(req, timeout=4) as reply:
            if reply.status != 200:
                stop('8018 測試服務未通過授權核對')
            raw = reply.read(256 * 1024 + 1)
            if len(raw) > 256 * 1024:
                stop('8018 測試資料量超出安全範圍')
            data = json.loads(raw)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, UnicodeError):
        stop('8018 尚未啟動，或測試簽章／資料庫驗證失敗。請確認 8018 仍在運行')
    if not isinstance(data, dict) or data.get('clinicId') != 'shanlin' or data.get('isSynthetic') is not True:
        stop('8018 回傳的資料來源並非山林合成測試資料')
    print('PASS: 8018 HMAC 唯讀驗證與獨立測試 Firebase 身分正確')
    print('PASS: 8006 既有資料檔、測試金鑰與本機儲存模式符合要求')
    return secret


def port_busy(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.6)
        return sock.connect_ex(('127.0.0.1', port)) == 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='read-only preflight; do not start')
    parser.add_argument('--port', type=int, choices=(8006, 8020), default=8020)
    args = parser.parse_args()
    secret = ready()
    if args.check:
        print('PASS: preflight only; no server started or data changed')
        return 0
    if port_busy(args.port):
        stop(f'{args.port} 已有服務在執行。不要強制關閉；請先到對應 Terminal 檢查')

    # The main website runs in local-demo mode without ANY Firebase credentials;
    # all synthetic booking reads/writes are delegated to signed localhost:8018.
    os.environ.update({
        'FIREBASE_URL': '', 'FIREBASE_CREDENTIALS': '',
        'PILOT_STORAGE': 'local-demo',
        'PILOT_SHANLIN_STORAGE': 'local-demo',
        'PILOT_YIDIAN_STORAGE': 'local-demo',
        'PILOT_V363_SERVICE_SECRET': secret,
        'PILOT_V365_SYNTHETIC_BOOKINGS_ENABLED': '1',
        'PILOT_SHANLIN_LEGACY_AUTH': '1',
        'PILOT_SHANLIN_LEGACY_URL': 'https://shanlin-bot-production.up.railway.app/api/admin/login',
    })
    os.chdir(SITE)
    print(f'PASS: 單一 DOUBTS 公版將在 http://127.0.0.1:{args.port}/pilot 啟動')
    print('注意：山林管理員登入仍需使用原正式帳號進行驗證；預約資料僅限獨立測試庫')
    import uvicorn
    uvicorn.run('integrated_app_platform_main:app', host='127.0.0.1', port=args.port,
                reload=False, log_level='info')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
