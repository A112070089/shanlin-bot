"""Install only brand-new DOUBTS v3.6 files, never overwrite legacy files.

Run from extracted package: python3 scripts/install_platform_v36.py --root ... [--apply]
Without --apply, checks only. Does not interact with Firebase/Railway/LINE.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from platform_phase36_preflight import check

PACKAGE = Path(__file__).resolve().parent.parent
RELATIVE = (
    'website/integrated_app_platform_v36.py',
    'website/platform_ops_evidence_v36.py',
    'website/platform_ops_routes_v36.py',
    'website/platform_static/clinic-operations-v36.html',
    'website/platform_static/clinic-operations-v36.js',
    'tests/test_platform_ops_v36.py',
    'scripts/platform_phase36_preflight.py',
    'scripts/install_platform_v36.py',
)


def inspect(root: Path) -> tuple[list[str], list[str]]:
    errors = check(root)
    changes: list[str] = []
    for relative in RELATIVE:
        src, target = PACKAGE / relative, root / relative
        if not src.is_file():
            errors.append('安裝包缺少檔案：'+relative)
        elif target.exists():
            if not target.is_file() or target.read_bytes() != src.read_bytes():
                errors.append('停止：公版已有不同版本的檔案，不允許覆寫：'+relative)
            else:
                changes.append('已安裝相同：'+relative)
        else:
            changes.append('將新增：'+relative)
    return errors, changes


def install(root: Path) -> tuple[list[str], list[str]]:
    problems, plans = inspect(root)
    if problems:
        return problems, plans
    created: list[Path] = []
    try:
        for relative in RELATIVE:
            src, target = PACKAGE / relative, root / relative
            if target.exists():
                continue
            target.parent.mkdir(parents=True,exist_ok=True)
            # O_EXCL prevents replacing even if a file appears after --check.
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            created.append(target)
            with os.fdopen(fd,'wb') as out:
                out.write(src.read_bytes())
                out.flush()
                os.fsync(out.fileno())
    except (OSError,ValueError) as exc:
        for path in reversed(created):
            try:path.unlink()
            except OSError:pass
        return ['安裝未完成且已還原本次新增檔案；錯誤類型：'+type(exc).__name__], plans
    return [], plans


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument('--root',required=True)
    p.add_argument('--apply',action='store_true')
    args=p.parse_args()
    root=Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print('STOP: 專案目錄不存在');return 2
    errors, plans=install(root) if args.apply else inspect(root)
    for info in plans:print(info)
    for error in errors:print('STOP:',error)
    if errors:return 2
    print('PASS:', '僅新增 v3.6 檔案，未修改 v3.5／Firebase／Railway' if args.apply else
          '唯讀預檢完成，可決定是否執行 --apply')
    return 0

if __name__=='__main__':sys.exit(main())
