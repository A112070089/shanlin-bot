"""Fail-closed, new-files-only DOUBTS v3.6.1 installer; nothing is deployed."""
from __future__ import annotations
import argparse
import ast
import os
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
FILES = (
    'website/integrated_app_platform_v361.py',
    'website/platform_shanlin_booking_source_v361.py',
    'website/platform_shanlin_booking_routes_v361.py',
    'sandbox/shanlin_readonly_sandbox_v361.py',
    'tests/test_platform_booking_v361.py',
    'scripts/install_platform_v361.py',
)
REQUIRED = (
    'website/integrated_app_platform_v36.py',
    'website/platform_ops_routes_v36.py',
    'website/pilot_backend.py',
    'website/platform_console.py',
    'tests/test_platform_ops_v36.py',
)


def inspect(root: Path):
    errors, planned = [], []
    for relative in REQUIRED:
        path = root / relative
        if not path.is_file():
            errors.append('缺少現有 v3.6 檔案：' + relative)
        elif path.suffix == '.py':
            try: ast.parse(path.read_text(encoding='utf-8'))
            except (SyntaxError, OSError, UnicodeError): errors.append('原始程式語法檢查失敗：'+relative)
    for relative in FILES:
        src, dst = PACKAGE / relative, root / relative
        if not src.is_file():
            errors.append('補丁遺失檔案：'+relative)
        elif dst.exists():
            if not dst.is_file() or dst.read_bytes() != src.read_bytes():
                errors.append('發現不同內容，絕不覆蓋：'+relative)
            else:
                planned.append('已安裝相同：'+relative)
        else:
            planned.append('將新增：'+relative)
    return errors, planned


def install(root: Path):
    errors, planned = inspect(root)
    if errors: return errors, planned
    created = []
    try:
        for relative in FILES:
            src, dst = PACKAGE / relative, root / relative
            if dst.exists(): continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            created.append(dst)
            with os.fdopen(fd,'wb') as output:
                output.write(src.read_bytes())
                output.flush()
                os.fsync(output.fileno())
    except OSError:
        for path in reversed(created):
            try: path.unlink()
            except OSError: pass
        return ['安裝失敗；已清除這次新增的檔案'], planned
    return [], planned


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    root=Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print('STOP: 找不到主專案資料夾');return 2
    errors,plans=install(root) if args.apply else inspect(root)
    for line in plans:print(line)
    for line in errors:print('STOP:',line)
    if errors:return 2
    print('PASS:', '只新增 v3.6.1 檔案；未修改原版、Firebase、Railway' if args.apply else '預檢完成；可進行 --apply')
    return 0

if __name__=='__main__':raise SystemExit(main())
