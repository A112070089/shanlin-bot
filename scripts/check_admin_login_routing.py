#!/usr/bin/env python3
"""Read-only 8006 admin routing smoke check; no password or private data used."""
from __future__ import annotations

import argparse
import json
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

ROOT = 'http://127.0.0.1:8006'
OFFICIAL = 'https://shanlin-bot-production.up.railway.app/admin.html'


def get(path):
    with urlopen(ROOT + path, timeout=8) as r:
        return r.status, r.read(750_000).decode('utf-8')


def main():
    status, html = get('/pilot?clinic=shanlin&view=admin')
    assert status == 200 and f'href="{OFFICIAL}"' in html, '山林後台 HTML 仍可能被導向本機舊版'
    print('PASS：山林正式後台 HTML 連結指向山林 Railway')

    status, script = get('/pilot/assets/pilot.js')
    assert status == 200 and OFFICIAL in script, '山林後台 JS 連結錯誤'
    assert '山林登入已停止：' not in script, '仍使用舊的誤導性登入錯誤文字'
    assert 'error.status=r.status' in script, '前端沒有區分 HTTP 狀態碼'
    print('PASS：兩診所共用登入流程，登入錯誤可分類')

    status, payload = get('/api/pilot/clinics/yidian/account-status')
    assert status == 200
    data = json.loads(payload)
    assert data.get('clinicId') == 'yidian'
    assert data.get('firebaseConnectionVerified') is False
    assert 'pilotStorage' in data
    print('PASS：頤典本機公版帳號狀態與 Firebase 連線驗證分開')
    print('    本機公版儲存模式：', data['pilotStorage'])
    print('    有提供本機公版 Firebase 設定：', data['pilotFirebaseCredentialsProvided'])
    print('    已實測 Firebase 連線：', data['firebaseConnectionVerified'])
    print('注意：這不代表頤典既有 Firebase 專案是否存在。')
    print('RESULT：本機 8006 後台路由唯讀檢查通過')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='本機後台路由唯讀檢查')
    parser.add_argument('--port', type=int, default=8006)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        raise SystemExit('STOP：埠號需介於 1 至 65535')
    ROOT = 'http://127.0.0.1:' + str(args.port)
    globals()['ROOT'] = ROOT
    try:
        main()
    except (AssertionError, HTTPError, URLError, TimeoutError) as exc:
        raise SystemExit('STOP：8006 尚未載入新版整合程式，或連線失敗：' + str(exc))
