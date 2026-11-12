#!/usr/bin/env python3
"""Apply dual-clinic username/password UI and server-side validation.

Atomic-per-file, backed up, all anchors verified before writing anything.
Neither reads nor writes patient data, Firebase credentials, or booking storage.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
import ast
import shutil
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
SITE=ROOT/'website'
MARKER='YIDIAN_UNIFIED_CLINIC_CREDENTIALS_V1'


def replace_exact(text, before, after, label):
    count=text.count(before)
    if count!=1:
        raise RuntimeError(f'STOP：{label} 錨點應有 1 處，實際 {count} 處；未修改任何檔案')
    return text.replace(before,after,1)


def change_backend(source):
    source=replace_exact(source,
        'class LegacyLoginIn(BaseModel):\n    password:str=Field(min_length=1,max_length=256)',
        'class LegacyLoginIn(BaseModel):\n    # The username is checked locally; Railway still verifies its existing password.\n'
        '    username:str=Field(min_length=4,max_length=64)\n'
        '    password:str=Field(min_length=1,max_length=256)',
        'API：山林帳號欄位強制必填')
    source=replace_exact(source,
        '    ip=check_login_limit(request)\n    if not verify_shanlin_legacy(body.password):fail_login(ip)\n'
        '    # Read legacy clinic settings only AFTER validating the original password.',
        "    ip=check_login_limit(request)\n"
        "    # A local tenant login identity (NOT a second Railway account).\n"
        "    # A wrong username must never trigger an upstream password attempt.\n"
        "    if not compare_digest(body.username, 'shanlin_admin'):fail_login(ip)\n"
        "    if not verify_shanlin_legacy(body.password):fail_login(ip)\n"
        '    # Read legacy clinic settings only AFTER validating the original password.',
        'API：山林帳號先驗證、密碼再交原 Railway')
    source=replace_exact(source,
        "token=new_session('shanlin',role='clinic_admin',username='shanlin_legacy')",
        "token=new_session('shanlin',role='clinic_admin',username=body.username)",
        'API：session 記錄山林登入帳號')
    source=replace_exact(source,
        "audit('shanlin_legacy_bridge_login','shanlin_legacy','shanlin')",
        "audit('shanlin_legacy_bridge_login',body.username,'shanlin')",
        'API：稽核使用相同帳號識別碼')
    source=replace_exact(source,
        "    if body.clinicId=='shanlin':\n"
        "        raise HTTPException(409,'山林沿用原有登入服務，請使用既有密碼登入')\n"
        '    ip=check_login_limit(request)',
        "    if body.clinicId=='shanlin':\n"
        "        # Same API contract for both clinics, independently verified.\n"
        '        return shanlin_login(\n'
        '            LegacyLoginIn(username=body.username,password=body.password),\n'
        '            request,response\n'
        '        )\n'
        '    ip=check_login_limit(request)',
        'API：兩診所共用帳號密碼登入路由')
    return source


def change_html(source):
    source=replace_exact(source,
        '<p id="clinicLoginNote">請使用所屬診所的管理憑證登入。兩家診所共用介面，但驗證方式與資料權限各自獨立。</p>',
        '<p id="clinicLoginNote">請輸入所屬診所的管理帳號與密碼。</p>',
        '登入頁：共用簡短副標')
    source=replace_exact(source,
        '        <div class="source-note clinic-login-info"><strong>沿用山林原有後台密碼</strong><p>不需要另外建立公版帳號；登入時會核對診所身分。</p></div>\n',
        '', '登入頁：移除山林大說明框')
    source=replace_exact(source,
        '        <form id="shanlinLoginForm" autocomplete="off">\n'
        '          <label>山林原後台管理密碼<input id="shanlinLoginPassword" name="shanlin_existing_backend_secret" type="password" maxlength="256" autocomplete="section-shanlin current-password" required placeholder="輸入山林原後台密碼"></label>',
        '        <form id="shanlinLoginForm" autocomplete="off">\n'
        '          <label>管理帳號<input id="shanlinLoginUsername" name="shanlin_clinic_username_v1" type="text" minlength="4" maxlength="64" autocomplete="section-shanlin username" required placeholder="例如：shanlin_admin"></label>\n'
        '          <label>管理密碼<input id="shanlinLoginPassword" name="shanlin_existing_backend_secret" type="password" maxlength="256" autocomplete="section-shanlin current-password" required placeholder="請輸入管理密碼"></label>',
        '登入頁：山林帳號與密碼欄')
    source=replace_exact(source,
        '<div id="yidianAccountNotice" class="source-note clinic-login-info" role="status">正在確認本機公版管理帳號設定…</div>',
        '<p id="yidianAccountNotice" class="small-note" role="status" hidden></p>',
        '登入頁：移除頤典 Firebase 技術說明大框')
    source=replace_exact(source,
        '<label>頤典診所管理帳號<input id="yidianLoginUsername"',
        '<label>管理帳號<input id="yidianLoginUsername"',
        '登入頁：頤典帳號欄文字一致')
    source=replace_exact(source,
        '<label>頤典管理密碼<input id="yidianLoginPassword"',
        '<label>管理密碼<input id="yidianLoginPassword"',
        '登入頁：頤典密碼欄文字一致')
    source=replace_exact(source,
        '        <p class="small-note">頤典管理帳號與山林原後台分離；Firebase 狀態以獨立連線檢查為準。</p>\n',
        '', '登入頁：移除頤典技術附註')
    source=replace_exact(source,
        '      <p class="small-note">請勿把其他診所的密碼輸入此頁；目前僅限本機示範，尚未連接正式預約與病歷資料。</p>\n',
        '', '登入頁：移除開發者附註')
    return source


def change_js(source):
    source=replace_exact(source,
        "    text('clinicLoginNote',entering==='shanlin'\n"
        "      ? '沿用山林正式後台管理密碼，並確認 Railway 回傳的診所確實屬於山林。'\n"
        "      : '請使用由頤典系統管理員建立的頤典專屬帳號，與山林原後台帳號不同。');",
        "    text('clinicLoginNote','請輸入所屬診所的管理帳號與密碼。');",
        '前端：移除不同登入提示')
    source=replace_exact(source,
        "      const state=String(status.notice || '本機公版 Firebase 連線尚未驗證。');\n"
        "      text('yidianAccountNotice',status.accountProvisioned\n"
        "        ? '頤典獨立管理帳號已建立。'+state\n"
        "        : '頤典管理帳號尚未建立，請由平台管理員開通。'+state);\n"
        "    }catch(err){if(clinic===expectedClinic)text('yidianAccountNotice','無法查詢帳號狀態：'+err.message);}",
        "      // No Firebase implementation details belong on the login screen.\n"
        "      $('yidianAccountNotice').hidden=!!status.accountProvisioned;\n"
        "      text('yidianAccountNotice',status.accountProvisioned?'':\n"
        "        '本診所尚未建立管理帳號，請聯絡平台管理員。');\n"
        "    }catch(err){\n"
        "      if(clinic===expectedClinic){\n"
        "        text('yidianAccountNotice','暫時無法確認管理帳號狀態，請稍後再試。');\n"
        "        $('yidianAccountNotice').hidden=false;\n"
        "      }\n"
        "    }",
        '前端：登入頁不再顯示 Firebase 開發者說明')
    source=replace_exact(source,
        "    try{\n      let sess;\n      if(loggingClinic==='shanlin'){\n"
        "        const p=$('shanlinLoginPassword').value;\n"
        "        $('shanlinLoginPassword').value='';\n"
        "        sess=await request('/admin/legacy-shanlin-login',{method:'POST',body:{password:p}});\n"
        "      }else{\n"
        "        const username=$('yidianLoginUsername').value.trim();\n"
        "        const p=$('yidianLoginPassword').value;\n"
        "        $('yidianLoginPassword').value='';\n"
        "        if(username==='shanlin_legacy'||username.toLowerCase().startsWith('shanlin')){\n"
        "          $('yidianLoginUsername').value='';\n"
        "          throw new Error('這是山林舊系統代號，不是頤典帳號。請使用平台管理員建立的頤典帳號。');\n"
        "        }\n"
        "        sess=await request('/admin/login',{method:'POST',body:{clinicId:loggingClinic,username,password:p}});\n"
        "      }\n"
        '      csrf=sess.csrf;',
        "    try{\n"
        "      const username=$(loggingClinic==='shanlin'?'shanlinLoginUsername':'yidianLoginUsername').value.trim();\n"
        "      const passwordField=$(loggingClinic==='shanlin'?'shanlinLoginPassword':'yidianLoginPassword');\n"
        "      const password=passwordField.value;\n"
        "      passwordField.value='';\n"
        "      // Both clinics use the same JSON login contract.\n"
        "      // Server checks the clinic-specific identity before issuing a session.\n"
        "      const sess=await request('/admin/login',{method:'POST',body:{\n"
        "        clinicId:loggingClinic,username,password\n"
        "      }});\n"
        '      csrf=sess.csrf;',
        '前端：兩家共用登入 API 且都傳 username/password')
    source=replace_exact(source,
        "    for(const id of ['shanlinLoginPassword','yidianLoginUsername','yidianLoginPassword']){",
        "    for(const id of ['shanlinLoginUsername','shanlinLoginPassword','yidianLoginUsername','yidianLoginPassword']){",
        '前端：兩家輸入即清除錯誤提示')
    return source


def change_css(source):
    if MARKER in source:
        raise RuntimeError('STOP：CSS 標記已存在；不重複安裝')
    return source+f'''\n\n/* {MARKER}: keep normal login screens free of implementation details. */\n#adminLogin #yidianAccountNotice[hidden]{{display:none!important}}\n#adminLogin #yidianAccountNotice:not([hidden]){{margin:8px 0 10px;color:#566e7e}}\n#adminLogin #shanlinLoginForm label,#adminLogin #yidianLoginForm label{{display:block}}\n'''


def change_old_tests(source):
    # These three previous tests intentionally used the retired password-only API.
    # Reassert their original security properties with the new mandatory username.
    if source.count("json={'password':'wrong-test'}") != 2:
        raise RuntimeError('STOP：舊測試 API 錨點不同，請先核對版本')
    if source.count("json={'password':'placeholder'}") != 2:
        raise RuntimeError('STOP：舊測試中山林驗證錨點不同，請先核對版本')
    source=source.replace("json={'password':'wrong-test'}",
                          "json={'username':'shanlin_admin','password':'wrong-test'}")
    source=source.replace("json={'password':'placeholder'}",
                          "json={'username':'shanlin_admin','password':'placeholder'}")
    return replace_exact(source,
        "        assert wrong.status_code == 409\n        ok = c.post('/api/pilot/admin/login', json={",
        "        assert wrong.status_code == 401\n        ok = c.post('/api/pilot/admin/login', json={",
        '舊測試：跨診所帳號改以中立 401 處理')


CHANGES={
 'website/pilot_backend.py':change_backend,
 'website/pilot_static/index.html':change_html,
 'website/pilot_static/pilot.js':change_js,
 'website/pilot_static/pilot.css':change_css,
 'tests/test_admin_login_routing.py':change_old_tests,
}


def main():
    # Safe to re-run after successful installation; never apply the patch twice.
    css_path=SITE/'pilot_static/pilot.css'
    if css_path.exists() and MARKER in css_path.read_text(encoding='utf-8'):
        required={
            SITE/'pilot_backend.py':"if not compare_digest(body.username, 'shanlin_admin'):fail_login(ip)",
            SITE/'pilot_static/index.html':'id="shanlinLoginUsername"',
            SITE/'pilot_static/pilot.js':"clinicId:loggingClinic,username,password",
        }
        if all(p.is_file() and text in p.read_text(encoding='utf-8') for p,text in required.items()):
            print('PASS：方案 A 已安裝，所有必要元件存在；無須重複修改。')
            return
        raise RuntimeError('STOP：找到部分安裝痕跡，請先檢查備份；未進行修改')
    preflight={}
    for relative,change in CHANGES.items():
        p=ROOT/relative
        if not p.is_file():raise RuntimeError(f'STOP：找不到 {relative}，未修改任何檔案')
        old=p.read_text(encoding='utf-8')
        if MARKER in old:
            raise RuntimeError(f'STOP：{relative} 已套用過補丁；不重複執行')
        new=change(old)
        if relative.endswith('.py'):ast.parse(new,filename=relative)
        preflight[p]=(relative,old,new)
    print('PASS：所有修改錨點及 Python 語法已確認；準備備份')
    backup=ROOT/'backups'/('unified_login_A_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
    backup.mkdir(parents=True,exist_ok=False)
    for p,(relative,old,new) in preflight.items():
        path=backup/relative;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(old,encoding='utf-8')
    written=[]
    try:
        for p,(relative,old,new) in preflight.items():
            with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=p.parent,
                                             prefix='.unified-login-',delete=False) as out:
                out.write(new);tmp=Path(out.name)
            try:
                tmp.chmod(p.stat().st_mode & 0o777)
                tmp.replace(p)
            except Exception:
                tmp.unlink(missing_ok=True);raise
            written.append(p)
    except Exception:
        for p in written:
            rel=preflight[p][0];shutil.copy2(backup/rel,p)
        raise
    print('PASS：兩診所登入頁已統一為帳號＋密碼')
    print('PASS：山林驗證帳號 shanlin_admin，沿用原 Railway 密碼')
    print('PASS：兩家都走 /api/pilot/admin/login，不共用帳號、密碼或資料')
    print('PASS：兩個大型登入說明框已移除，登入限制保留')
    print('備份：',backup)
    print('下一步：./.venv/bin/python -m pytest -q tests')

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(str(exc),file=sys.stderr)
        sys.exit(1)
