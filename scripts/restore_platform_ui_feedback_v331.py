#!/usr/bin/env python3
"""Safely restore DOUBTS v3.3 static UI files from the installation backup."""
from pathlib import Path
from hashlib import sha256
import os
import shutil
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
BACKUP=ROOT/'backups'/'platform_ui_feedback_v331'
CHECKSUMS={'website/platform_static/platform-v321.js': {'original': 'c61f5d946357b95dcc4d10a8fb854e368f76db821f3a42c6d0ece19493d1b1fe', 'patched': 'c99628d863090dd029fafe6a405e388cde97d92f0ebb2920d788df92e26c0d44'}, 'website/platform_static/platform.css': {'original': 'f82d9e5d701b471708c92df9ab64708499b6dc63cf153625940e4705a1782f1a', 'patched': 'c27b2b19d1221a7750ae8fb0dc5d6a424cfac1e2b89268705e5cea2d91d67fe9'}, 'website/platform_static/module-release-v33.js': {'original': '143e01ea95302945ae051b43feffb56f0ffdd127d1aa598422f20196645585b8', 'patched': '5261135cd9cdcecc39b6cd61d7afaefd2a5577e790687045a3f19770d4d08e22'}, 'website/platform_static/module-release-v33.html': {'original': 'acd7f4bb00455fb584fe586aebbc98495936c89be20ff5bcce0b75a0047542d1', 'patched': '9b85515e15b32cf2ebb930026e25ddb772cc1493f78bbdcb5b4ad975f2eff259'}, 'website/platform_static/module-release-v33.css': {'original': '9ba4e6a7fb9b7b4c7a269fbb60a9837ab65685ba22f419234dc29c8b9b0013a4', 'patched': '392c4472acea4cbb90ab103095d6f92c9cf28885b5f0c2b8cdf48670bcff7a67'}}


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def main():
    changes=[]
    for relative, sha in CHECKSUMS.items():
        dest=ROOT/relative
        backup=BACKUP/relative
        if not dest.is_file() or dest.is_symlink():
            raise RuntimeError(f'檔案不存在：{relative}')
        current=digest(dest)
        if current == sha['original']:
            continue
        if current != sha['patched']:
            raise RuntimeError(f'檔案已被其他修改，為避免覆蓋而停止：{relative}')
        if not backup.is_file() or backup.is_symlink() or digest(backup)!=sha['original']:
            raise RuntimeError(f'找不到可驗證的原始備份：{relative}')
        changes.append((backup,dest))
    for backup,dest in changes:
        with tempfile.NamedTemporaryFile(prefix='.restore-v331-',dir=dest.parent,delete=False) as tmp:
            temp=Path(tmp.name)
        try:
            shutil.copyfile(backup,temp)
            os.chmod(temp,dest.stat().st_mode & 0o777)
            os.replace(temp,dest)
            print('已還原：',dest.relative_to(ROOT))
        finally:
            temp.unlink(missing_ok=True)
    print('PASS：v3.3 UI 已還原；資料與帳號未變更。')


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('STOP：'+str(exc),file=sys.stderr)
        sys.exit(1)
