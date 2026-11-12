"""Reuse the EXISTING pilot platform administrator; never print/store plaintext.

Usage: python scripts/setup_platform_console.py status
       python scripts/setup_platform_console.py init
"""
from pathlib import Path
import getpass
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'website'))
import pilot_backend  # noqa: E402


def main():
    arg = sys.argv[1] if len(sys.argv) == 2 else 'status'
    if arg == 'status':
        print('平台管理員帳號：', '已建立，可直接登入' if pilot_backend.platform_account_exists()
              else '尚未建立，請執行 init')
        print('登入入口（啟動 8006 後）：http://127.0.0.1:8006/platform/admin')
        return
    if arg != 'init':
        raise SystemExit('使用方式：python scripts/setup_platform_console.py [status|init]')
    if pilot_backend.platform_account_exists():
        print('STOP：現有平台管理員帳號已存在；不會重設或建立第二組密碼。')
        return
    name = input('請設定工程師帳號（Enter 預設 platform_admin）：').strip() or 'platform_admin'
    secret = getpass.getpass('設定工程師密碼（至少 12 字元，不顯示）：')
    verify = getpass.getpass('再次輸入工程師密碼：')
    if secret != verify:
        raise SystemExit('STOP：兩次密碼不同，未建立帳號')
    try:
        pilot_backend.setup_platform_account(name, secret)
    except ValueError as exc:
        raise SystemExit(f'STOP：{exc}') from exc
    finally:
        del secret, verify
    print('PASS：沿用公版既有平台帳號系統建立工程師管理員')
    print('登入入口：http://127.0.0.1:8006/platform/admin')


if __name__ == '__main__':
    main()
