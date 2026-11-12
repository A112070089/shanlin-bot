#!/usr/bin/env python3
"""Read-only v3.2 module registry health and legacy migration report.

Runs from project root: ./.venv/bin/python scripts/check_platform_modules_v32.py
No HTTP, Firebase, patient data, credential readback or database writes.
"""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'website'))
import platform_module_store_v32 as store


def main():
    state=store.read_state()
    path,_=store._paths()
    print('=== DOUBTS 工程師平台 v3.2 動態功能模組唯讀檢查 ===')
    print('v3.2 設定檔：', '已建立' if path.exists() else '尚未建立（首次儲存會匯入舊設定）')
    print('功能模組：',len(state['modules']))
    print('診所清單：',len(state['clinics']))
    print('已驗證部署：',sum(x['deployment']=='deployed' for x in state['modules']))
    print('預先授權數：',sum(v is True for row in state['grants'].values() for v in row.values()))
    for c in state['clinics']:
        print(' -',c['id'],c['name'], '(既有診所)' if c['kind']=='existing' else '(導入草稿)',
              '可設定' if c['active'] else '已停用')
    assert all(x['deployment']!='deployed' for x in state['modules']) or store.VERIFIED_RUNTIME_ADAPTERS
    print('PASS：功能登錄表可讀取；未對 Firebase、病患資料或正式預約進行操作')

if __name__=='__main__':
    main()
