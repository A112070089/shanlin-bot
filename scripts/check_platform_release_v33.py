#!/usr/bin/env python3
"""Read-only v3.3 release/acceptance report. No network, no writes to records."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'website'))

import platform_release_store_v33 as rel
import platform_standard_policy_v321 as plan


def main():
    data=rel.list_releases()
    records={x['moduleId']:x for x in data['releases']}
    print('=== DOUBTS v3.3 模組部署／驗收檢查（唯讀）===')
    print('功能模組總數：',len(records))
    for item in plan.read_state()['modules']:
        r=records[item['id']]
        print(f"- {item['name']} ({item['id']})｜{r['version']}｜開發={r['progress']}｜驗收={r['acceptance']}｜部署驗證={r['deploymentVerified']}")
    print('標準版範圍：所有符合條件的合作診所共用；無逐家付費功能勾選')
    print('實際啟用：仍須驗收核准＋可信任的程式部署驗證＋診所開通驗收')
    print('資料操作：不修改 Firebase、預約、模組設定或驗收檔案')
    print('PASS：v3.3 唯讀檢查完成')

if __name__ == '__main__':
    main()
