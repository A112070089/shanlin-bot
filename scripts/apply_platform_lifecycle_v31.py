"""Safely install DOUBTS engineer clinic lifecycle v3.1 over exact V3 code.

Never accesses clinic patient data, Firebase, production bookings or secrets.
Backups are made before file replacement; repeat execution is idempotent.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / 'scripts' / 'v31_payload'
MANIFEST = PAYLOAD / 'manifest.json'
BACKUP = ROOT / 'backups' / 'platform_lifecycle_v31'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if not (ROOT/'website/integrated_app_platform_v3.py').is_file():
        raise SystemExit('STOP：請先安裝並測試 v3 開通管理版本，尚未修改檔案')
    if not MANIFEST.is_file():
        raise SystemExit('STOP：缺少 v3.1 安裝清單，未修改檔案')
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    replacements = manifest['replacement_files']
    news = manifest['new_files']
    operations = []
    for name, hashes in replacements.items():
        dest = ROOT/name
        source = PAYLOAD/name
        if (not dest.is_file() or dest.is_symlink() or not source.is_file()
                or source.is_symlink() or digest(source) != hashes['new_sha256']):
            raise SystemExit('STOP：找不到必要檔案或補丁資料異常：'+name)
        current = digest(dest)
        if current == hashes['new_sha256']:
            continue
        if current not in hashes.get('allowed_old_sha256',[hashes['old_sha256']]):
            raise SystemExit('STOP：現有程式已被另外修改，為保護原有程式，不覆蓋：'+name)
        operations.append((name, dest, source, True))
    for name, target_sha in news.items():
        dest = ROOT/name
        source = PAYLOAD/name
        if not source.is_file() or source.is_symlink() or digest(source) != target_sha:
            raise SystemExit('STOP：補丁資料異常：'+name)
        if dest.exists() or dest.is_symlink():
            if not dest.is_file() or dest.is_symlink() or digest(dest) != target_sha:
                raise SystemExit('STOP：將新增的檔案已有其他內容，拒絕覆蓋：'+name)
        else:
            operations.append((name, dest, source, False))
    if not operations:
        print('PASS：v3.1 已安裝，無須重複修改任何檔案')
        return
    # All preflight checks finished. Ensure backup copies exist BEFORE changes.
    for name, dest, source, existing in operations:
        if existing:
            backup=BACKUP/name
            backup.parent.mkdir(parents=True,exist_ok=True)
            if not backup.exists():
                shutil.copy2(dest,backup)
            elif digest(backup)!=digest(dest):
                raise SystemExit('STOP：既有備份與目前原始檔不同，為安全起見拒絕覆蓋：'+name)
    for name, dest, source, existing in operations:
        dest.parent.mkdir(parents=True,exist_ok=True)
        fd,tmp=tempfile.mkstemp(prefix='.v31-',suffix='.tmp',dir=str(dest.parent))
        try:
            with os.fdopen(fd,'wb') as handle:
                handle.write(source.read_bytes())
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp,dest)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
        print('PASS：'+name)
    print('PASS：v3.1 已安裝，原有四個檔案已備份於 backups/platform_lifecycle_v31/')
    print('說明：未存取 Firebase、Railway、預約、原診所及任何病患資料')


if __name__=='__main__':
    main()
