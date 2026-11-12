"""Make the engineer clinic center ask for credentials directly when signed out.

Safely patches ONLY the clinic center's existing UI and engineer login redirect.
This never touches Firebase, patient data, appointment routes or stored flags.
"""
from __future__ import annotations

from pathlib import Path
import os
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]

# Exact, idempotent replacements. Reject unexpected versions instead of guessing.
CHANGES: dict[str, list[tuple[str, str]]] = {
    'website/platform_static/clinic-center.html': [
        ('<main><h1>診所管理中心</h1>', '<main id="clinicCenterMain" hidden><h1>診所管理中心</h1>'),
    ],
    'website/platform_static/clinic-center.js': [
        (
            "await reload();$('content').hidden=false;message('已登入工程師總控台；目前只能建立本機導入草稿。');}catch(e){message('請先以工程師帳號登入總控台。');const link=document.createElement('a');link.href='/platform/admin';link.textContent='前往工程師登入';$('status').append(' ',link);}})();",
            "await reload();$('clinicCenterMain').hidden=false;$('content').hidden=false;message('已登入工程師總控台；目前只能建立本機導入草稿。');}catch(e){if(e.status===401||e.status===403){location.replace('/platform/admin?next=%2Fplatform%2Fclinics');return;}$('clinicCenterMain').hidden=false;message('目前無法載入診所管理中心：'+e.message);}})();",
        ),
    ],
    'website/platform_static/platform.js': [
        (
            "'use strict';\nconst $=id=>document.getElementById(id);",
            "'use strict';\n// Fixed allowlist: never navigate to arbitrary query-supplied URLs.\nconst CLINIC_CENTER_AFTER_LOGIN = new URLSearchParams(location.search).get('next') === '/platform/clinics' ? '/platform/clinics' : '';\nconst $=id=>document.getElementById(id);",
        ),
        (
            "csrf=s.csrf;showDashboard(true);await load();}catch{",
            "csrf=s.csrf;if(CLINIC_CENTER_AFTER_LOGIN){location.replace(CLINIC_CENTER_AFTER_LOGIN);return;}showDashboard(true);await load();}catch{",
        ),
        (
            "csrf=s.csrf;$('password').value='';$('loginMessage').textContent='';showDashboard(true);await load();}catch(err){",
            "csrf=s.csrf;$('password').value='';$('loginMessage').textContent='';if(CLINIC_CENTER_AFTER_LOGIN){location.replace(CLINIC_CENTER_AFTER_LOGIN);return;}showDashboard(true);await load();}catch(err){",
        ),
    ],
}


def transformed(src: str, replacements: list[tuple[str, str]], filename: str) -> tuple[str, bool]:
    changed = False
    result = src
    for old, new in replacements:
        if result.count(new) == 1 and old not in result:
            continue  # Replacement already applied.
        if result.count(old) != 1 or result.count(new) != 0:
            raise RuntimeError(f'STOP: {filename} 版本不符，沒有修改任何檔案')
        result = result.replace(old, new, 1)
        changed = True
    return result, changed


def main() -> None:
    original = {}
    modified = {}
    for relative, replacements in CHANGES.items():
        path = ROOT / relative
        if not path.is_file():
            raise SystemExit(f'STOP: 找不到 {relative}，沒有修改任何檔案')
        data = path.read_text(encoding='utf-8')
        try:
            result, changed = transformed(data, replacements, relative)
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc
        original[relative] = data
        if changed:
            modified[relative] = result

    if not modified:
        print('PASS：登入導頁補丁已安裝，無須重複修改')
        return

    backup_dir = ROOT / 'backups' / 'platform_clinic_direct_login_v21'
    for relative in modified:
        backup = backup_dir / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            shutil.copy2(ROOT / relative, backup)

    written = []
    try:
        for relative, content in modified.items():
            path = ROOT / relative
            mode = path.stat().st_mode & 0o777
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, prefix='.login-v21-', delete=False) as tmp:
                tmp.write(content)
                tmp_name = Path(tmp.name)
            try:
                os.chmod(tmp_name, mode)
                os.replace(tmp_name, path)
                written.append(relative)
            finally:
                if tmp_name.exists():
                    tmp_name.unlink()
    except Exception:
        for relative in written:
            (ROOT / relative).write_text(original[relative], encoding='utf-8')
        raise

    print('PASS：已移除未登入時的中繼提示頁')
    print('PASS：未登入直接跳轉工程師帳密頁，成功登入後返回診所管理中心')
    print('PASS：保留原本登入驗證、CSRF 與診所資料隔離')
    print('備份資料夾：', backup_dir)


if __name__ == '__main__':
    main()
