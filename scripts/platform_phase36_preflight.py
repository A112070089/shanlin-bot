"""Read-only checks of an existing DOUBTS source tree; prints no secrets/PII."""
from pathlib import Path
import argparse
import ast
import sys

REQUIRED = (
 'website/integrated_app_platform_v35.py',
 'website/platform_console.py',
 'website/platform_static/admin-v321.html',
 'website/pilot_backend.py',
 'website/platform_standard_policy_v321.py',
 'website/integrated_app_clinics.py',
 'website/pilot_shanlin_catalog.py',
)


def check(root):
    issues=[]
    for name in REQUIRED:
        path=root/name
        if not path.is_file(): issues.append('找不到既有檔案：'+name)
    python_files=list((root/'website').glob('integrated_app_platform*.py'))
    for path in python_files:
        try: ast.parse(path.read_text(encoding='utf-8'))
        except (SyntaxError,UnicodeError,OSError): issues.append('語法或編碼檢查失敗：'+path.name)
    html=root/'website/platform_static/admin-v321.html'
    if html.exists():
        expected='<a href="/platform/modules">功能模組管理中心 →</a>'
        if html.read_text(encoding='utf-8').count(expected)!=1:
            issues.append('原工程師首頁版本已變更，不能自動加入新入口')
    return issues


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',required=True)
    a=p.parse_args();root=Path(a.root).expanduser()
    issues=check(root)
    print('DOUBTS v3.6 公版相容性預檢（唯讀）')
    if issues:
        for line in issues:print('STOP:',line)
        return 2
    print('PASS: 既有公版檔案與首頁定位符合已知結構。此結果不代表正式預約已可上線。')
    return 0

if __name__=='__main__':sys.exit(main())
