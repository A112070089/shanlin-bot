#!/usr/bin/env python3
"""Surgical, rollback-capable phase 8 clinic login/routing fix.

Run from project root, after taking a project backup. Only five audited files
are modified. Nothing in patient, catalog, appointment or Firebase data is read
or written. The installer checks *all* anchors before writing any file.
"""
from __future__ import annotations

import ast
from datetime import datetime
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'website'
VERSION_TAG = 'CLINIC_LOGIN_ROUTING_FIX_V1'


def one(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f'{label}：預期找到一次，實際找到 {count} 次；停止所有修改')
    return source.replace(old, new, 1)


def change_site(source: str) -> str:
    source = one(source,
        '    html = html.replace("https://shanlin-bot-production.up.railway.app/admin.html", "/admin.html")\n'
        '    html = html.replace("http://127.0.0.1:5500/admin.html", "/admin.html")',
        '    # The original Shanlin Railway admin is a separate verified origin.\n'
        '    # NEVER rewrite that link to local /admin.html (the old Yidian page).\n'
        '    html = html.replace("http://127.0.0.1:5500/admin.html",\n'
        '                        "https://shanlin-bot-production.up.railway.app/admin.html")',
        '正式山林 HTML 連結')
    source = one(source,
        '    js = js.replace("https://shanlin-bot-production.up.railway.app/admin.html", "/admin.html")\n'
        '    return Response(js, media_type="application/javascript", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})',
        '    # Do not redirect Shanlin staff to this host\'s legacy /admin.html.\n'
        '    return Response(js, media_type="application/javascript", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})',
        '正式山林 JS 連結')
    return source


def change_backend(source: str) -> str:
    source = one(source, """def tenant_provisioning_state():
    # Presence is not a successful cloud connection test.
    result={}
    for clinic in CLINICS:
        prefix='PILOT_'+clinic.upper()+'_'
        ready=bool(os.getenv(prefix+'FIREBASE_URL','').strip() and
                   os.getenv(prefix+'FIREBASE_CREDENTIALS','').strip())
        result[clinic]={'pilotFirebaseCredentialsProvided':ready,
                        'pilotFirebaseConnected':False,
                        'pilotStorage':STORAGE_MODE,
                        'notice':('已提供設定，但未測試連線；不可視為已開通' if ready else '未開通公版專屬 Firebase')}
    return result
""", """def tenant_provisioning_state():
    # This only describes the PILOT process, NOT whether a Firebase project exists.
    # Env-variable presence is never a connection or successful write/read test.
    result = {}
    for clinic in CLINICS:
        prefix = 'PILOT_' + clinic.upper() + '_'
        configured = bool(os.getenv(prefix+'FIREBASE_URL','').strip() and
                          os.getenv(prefix+'FIREBASE_CREDENTIALS','').strip())
        mode = clinic_storage_mode(clinic)
        if configured and mode == 'firebase':
            note = '本機公版已設定 Firebase 模式；尚未驗證資料庫連線。'
        elif configured:
            note = '已提供公版專用 Firebase 設定，但目前仍使用本機資料。'
        else:
            note = '本機公版未提供獨立 Firebase 設定；無法由此判斷 Firebase 專案是否已建立。'
        result[clinic] = {
            'pilotFirebaseCredentialsProvided': configured,
            'pilotFirebaseConnected': False,
            'pilotFirebaseConnectionVerified': False,
            'pilotStorage': mode,
            'notice': note,
        }
    return result
""", '公版 Firebase 證據狀態')
    source = one(source, """@router.get('/api/pilot/clinics/yidian/account-status')
def yidian_account_status(response:Response):
    response.headers['Cache-Control']='no-store'
    # A username/password must be created by the platform administrator.
    # The existence of a local account is NOT evidence of Firebase connection.
    return {'clinicId':'yidian', 'accountProvisioned':bool(_account_data('yidian')),
            'firebaseConnected':False, 'storage':'local-pilot'}
""", """@router.get('/api/pilot/clinics/yidian/account-status')
def yidian_account_status(response:Response):
    response.headers['Cache-Control'] = 'no-store'
    state = tenant_provisioning_state()['yidian']
    # Distinguish account login, pilot storage mode and externally provisioned
    # Firebase. Do not mistake an unverified connection for a missing project.
    return {
        'clinicId': 'yidian',
        'accountProvisioned': bool(_account_data('yidian')),
        'pilotStorage': state['pilotStorage'],
        'pilotFirebaseCredentialsProvided': state['pilotFirebaseCredentialsProvided'],
        'firebaseConnected': None,  # unknown: not tested, NOT disconnected
        'firebaseConnectionVerified': False,
        'notice': state['notice'],
    }
""", '頤典登入頁資料庫狀態 API')
    source = one(source, """    ],'storage':STORAGE_MODE,'firebaseProvisioning':tenant_provisioning_state(),
      'notice':'山林的既有 Firebase 與公版儲存分開；頤典尚未開通 Firebase 時只用獨立本機試行資料'}""", """    ],'storage':STORAGE_MODE,'firebaseProvisioning':tenant_provisioning_state(),
      'notice':'各診所 Firebase 與本機公版設定彼此獨立；未檢測連線時不得宣稱資料庫未開通。'}""", '平台 Firebase 說明')
    source = one(source, """                'url':'http://127.0.0.1:5500/admin.html',
                'legacyConfigRead':verified,'legacyConfigReadAt':sess.get('legacyConfigReadAt'),""", """                'url':('https://shanlin-bot-production.up.railway.app/admin.html'
                       if verified else None),
                'legacyConfigRead':verified,'legacyConfigReadAt':sess.get('legacyConfigReadAt'),""", '山林正式後台 API URL')
    source = one(source, """    return {'clinicId':clinic,'connected':False,'mode':'not_configured',
            'label':(
                '頤典公版已設定獨立 Firebase；正式預約尚未串接'
                if yidian_firebase_configured else
                '頤典公版尚未完成 Firebase 設定；正式預約尚未串接'
            ), 'url':None,""", """    return {'clinicId':clinic,'connected':False,'mode':'pilot_storage_unverified',
            'label':(
                '頤典公版已設定使用 Firebase（連線未驗證）；正式預約尚未串接'
                if yidian_firebase_configured else
                '頤典公版目前未驗證 Firebase 連線；正式預約尚未串接'
            ), 'url':None,""", '頤典整合狀態標籤')
    source = one(source, """            'originalCatalogCount':0,'yidianFirebaseConnected':False,
            'firebaseCredentialsProvided':firebase['pilotFirebaseCredentialsProvided'],
            'writebackToLegacySite':False,
            'details':(
                '頤典公版已設定使用專屬 Firebase，仍需驗證公版寫入與讀回。'
                '正式預約及病歷系統尚未串接。'
                if yidian_firebase_configured else
                '目前公版尚未完成 Firebase 設定；正式預約及病歷系統尚未串接。'
            )}""", """            'originalCatalogCount':0,'yidianFirebaseConnected':None,
            'firebaseConnectionVerified':False,
            'pilotStorage':clinic_storage_mode('yidian'),
            'firebaseCredentialsProvided':firebase['pilotFirebaseCredentialsProvided'],
            'writebackToLegacySite':False,
            'details':(
                '頤典本機公版設定為專屬 Firebase 模式，仍須獨立驗證連線。'
                '正式預約與病歷系統尚未串接。'
                if yidian_firebase_configured else
                '本機公版尚未驗證 Firebase 連線；這不代表既有頤典 Firebase 專案未開通。'
                '正式預約與病歷系統尚未串接。'
            )}""", '頤典整合狀態詳細說明')
    return source


def change_html(source: str) -> str:
    source = one(source,
        '      <p id="clinicLoginNote">使用診所專屬帳號及密碼登入，僅能管理所屬診所的資料。</p>',
        '      <p id="clinicLoginNote">請使用所屬診所的管理憑證登入。兩家診所共用介面，但驗證方式與資料權限各自獨立。</p>',
        '登入頁共同說明')
    source = one(source,
        '        <div class="source-note"><strong>山林沿用既有密碼，沒有第二組「公版帳號」。</strong><p>系統會驗證登入身分與診所歸屬，以保護各診所資料安全。</p></div>',
        '        <div class="source-note clinic-login-info"><strong>沿用山林原有後台密碼</strong><p>不需要另外建立公版帳號；登入時會核對診所身分。</p></div>',
        '山林帳號說明')
    source = one(source,
        '          <button class="primary-button" type="submit">驗證山林原後台</button>',
        '          <button id="shanlinLoginButton" class="primary-button" type="submit">登入診所管理後台</button>',
        '山林登入按鈕')
    source = one(source,
        '<div id="shanlinLoginError" class="source-note source-error" role="alert" hidden></div>',
        '<div id="shanlinLoginError" class="clinic-login-error" role="alert" hidden></div>',
        '山林登入錯誤區')
    source = one(source,
        '<div id="yidianAccountNotice" class="source-note" role="status">正在確認頤典管理帳號是否已由平台開通…</div>',
        '<div id="yidianAccountNotice" class="source-note clinic-login-info" role="status">正在確認本機公版管理帳號設定…</div>',
        '頤典登入狀態卡')
    source = one(source,
        '<button id="yidianLoginButton" class="primary-button" type="submit">登入頤典診所管理後台</button>',
        '<button id="yidianLoginButton" class="primary-button" type="submit">登入診所管理後台</button>',
        '頤典登入按鈕')
    source = one(source,
        '        </form>\n        <button id="goYidianProvision" class="outline-button" type="button" hidden>',
        '        </form>\n        <div id="yidianLoginError" class="clinic-login-error" role="alert" hidden></div>\n'
        '        <button id="goYidianProvision" class="outline-button" type="button" hidden>',
        '頤典登入錯誤區')
    source = one(source,
        '        <p class="small-note">本機頤典帳號與山林完全分離，且不代表頤典已開通 Firebase。</p>',
        '        <p class="small-note">頤典管理帳號與山林原後台分離；Firebase 狀態以獨立連線檢查為準。</p>',
        '頤典登入補充說明')
    source = one(source,
        '<div id="platformFirebaseNotice" class="source-note" role="status">頤典目前沒有獨立 Firebase；開通帳號不代表已開通資料庫。請勿填入山林的 Firebase 憑證。</div>',
        '<div id="platformFirebaseNotice" class="source-note" role="status">正在檢查本機公版 Firebase 設定；帳號開通不等於資料庫連線已驗證。</div>',
        '平台 Firebase 狀態預設')
    source = one(source,
        '        <p class="small-note">如來源名稱或地址不對，請勿匯入。頤典 Firebase 仍未開通；此頁後續修改只儲存到頤典自己的本機資料區。</p>',
        '        <p class="small-note">如來源名稱或地址不對，請勿匯入。資料儲存位置以公版環境設定為準；未完成驗證前勿混用診所資料。</p>',
        '隱藏預覽區狀態說明')
    return source


def change_js(source: str) -> str:
    source = one(source,
        "      throw new Error(detail);",
        "      const error=new Error(detail);\n      error.status=r.status;\n      throw error;",
        'HTTP 錯誤碼保留')
    source = one(source, """    $('shanlinLoginError').hidden=true;
    $('yidianLoginPassword').value='';""", """    $('shanlinLoginError').hidden=true;
    $('yidianLoginError').hidden=true;
    $('yidianLoginPassword').value='';""", '切換診所時清除兩邊提示')
    source = one(source, """      text('yidianAccountNotice',status.accountProvisioned
        ? '頤典獨立管理帳號已開通，可登入本機資料區。頤典 Firebase 尚未開通。'
        : '頤典管理帳號尚未建立。請先用「頤典系統管理」開通，不得使用 shanlin_legacy 或山林原密碼。');""", """      const state=String(status.notice || '本機公版 Firebase 連線尚未驗證。');
      text('yidianAccountNotice',status.accountProvisioned
        ? '頤典獨立管理帳號已建立。'+state
        : '頤典管理帳號尚未建立，請由平台管理員開通。'+state);""", '頤典 Firebase 登入說明')
    source = one(source, """  async function login(event){
    event.preventDefault();if(!clinic)return;
    const loggingClinic=clinic;
    try{
      let sess;""", """  let loginInFlight=false;
  function loginFailureMessage(err, which){
    if(err.status===401)return '帳號或密碼不正確，請再試一次。';
    if(err.status===429)return '登入嘗試次數較多，請稍後再試。';
    if(err.status===409)return which==='shanlin'
      ? '本次登入未完成：無法確認山林原後台的診所歸屬。請管理者核對來源設定。'
      : '帳號與所選診所不符，請確認登入入口。';
    if(err.status===503 || (err.status>=500))return '驗證服務暫時無法連線，請稍後再試。';
    return '登入未完成，請確認資料及網路連線後再試。';
  }
  async function login(event){
    event.preventDefault();if(!clinic || loginInFlight)return;
    const loggingClinic=clinic;
    const submit=$((loggingClinic==='shanlin')?'shanlinLoginButton':'yidianLoginButton');
    const wasDisabled=submit.disabled;
    loginInFlight=true;submit.disabled=true;
    $('shanlinLoginError').hidden=true;
    $('yidianLoginError').hidden=true;
    try{
      let sess;""", '登入流程防重送與錯誤分類')
    source = one(source, """    }catch(err){
      if(loggingClinic==='shanlin'){text('shanlinLoginError','山林登入已停止：'+err.message+'。請先核對山林 Railway 的診所設定與資料庫歸屬，不要在另一家診所的資料庫上重試。');$('shanlinLoginError').hidden=false;}
      toast(err.message,true);
    }
  }
  async function openPlatform(){""", """    }catch(err){
      const message=loginFailureMessage(err,loggingClinic);
      const errorBox=$(loggingClinic==='shanlin'?'shanlinLoginError':'yidianLoginError');
      if(clinic===loggingClinic){errorBox.textContent=message;errorBox.hidden=false;}
      // Inline feedback is enough: avoid a second alarming red toast.
    }finally{
      loginInFlight=false;
      // Restore the original state; do not re-enable an unprovisioned account.
      submit.disabled=wasDisabled;
    }
  }
  async function openPlatform(){""", '失敗提示和原安全限制')
    source = one(source, """        const desc=document.createElement('p');desc.textContent=item.clinicId==='shanlin'
          ? '使用山林 Railway 後台登入驗證，不重新設定原密碼。'
          : item.provisioned?('已建立本機試行帳號：'+item.username+'；頤典 Firebase 尚未開通')
                           :'尚未開通登入帳號，也沒有頤典 Firebase；請由平台管理員先建立。';""", """        const desc=document.createElement('p');desc.textContent=item.clinicId==='shanlin'
          ? '沿用山林 Railway 原後台密碼；不會另外建立公版密碼。'
          : item.provisioned?('已建立本機公版帳號：'+item.username+'。Firebase 狀態須另外驗證。')
                           :'本機公版管理帳號尚未建立，請由平台管理員開通。';""", '平台帳號說明')
    source = one(source, """      text('platformFirebaseNotice', '頤典 Firebase：'+(yidianDb?.pilotFirebaseCredentialsProvided?'有提供獨立設定（尚未驗證連線）':'尚未開通')+
            '。山林原有 Firebase 獨立保留，兩家資料不得混用。');""", """      text('platformFirebaseNotice', '頤典：'+(yidianDb?.notice || '尚未確認本機公版資料庫設定')+
            ' 山林與頤典使用獨立資料來源，不得共用服務帳戶或資料庫路徑。');""", '平台 Firebase 設定文案')
    source = one(source, """      const showShanlinLink=
        clinic==='shanlin' && state.mode==='legacy_admin_link';

      $('openLegacyAdmin').hidden=!showShanlinLink;

      if(showShanlinLink){
        $('openLegacyAdmin').href=
          'https://shanlin-bot-production.up.railway.app/admin.html';
      }""", """      const official='https://shanlin-bot-production.up.railway.app/admin.html';
      const showShanlinLink=clinic==='shanlin' && state.mode==='legacy_admin_link'
        && state.legacyConfigRead===true && state.url===official;
      $('openLegacyAdmin').hidden=!showShanlinLink;
      if(showShanlinLink){$('openLegacyAdmin').href=official;}
      else{$('openLegacyAdmin').removeAttribute('href');}""", '正式後台連結驗證')
    source = one(source,
        "    $('yidianLoginForm').addEventListener('submit',login);",
        "    $('yidianLoginForm').addEventListener('submit',login);\n"
        "    for(const id of ['shanlinLoginPassword','yidianLoginUsername','yidianLoginPassword']){\n"
        "      $(id).addEventListener('input',()=>{\n"
        "        $('shanlinLoginError').hidden=true;$('yidianLoginError').hidden=true;\n"
        "      });\n"
        "    }",
        '登入錯誤提示輸入時重設')
    return source


def change_css(source: str) -> str:
    return source + """

/* CLINIC_LOGIN_ROUTING_FIX_V1: consistent visual login feedback for both clinics. */
#adminLogin .clinic-login-info{margin:18px 0 8px;min-height:90px}
#adminLogin .clinic-login-info p{margin:6px 0 0}
#adminLogin .clinic-login-error{margin:12px 0 0;padding:11px 14px;
  background:#fff6ef;color:#8a4a2c;border:1px solid #eacbb2;
  border-radius:10px;font-size:15px;line-height:1.55}
#adminLogin .clinic-login-error[hidden]{display:none!important}
#adminLogin .primary-button{min-height:48px}
@media(max-width:620px){#adminLogin .clinic-login-info{min-height:auto}}
"""


FILES = {
    'website/integrated_site.py': change_site,
    'website/pilot_backend.py': change_backend,
    'website/pilot_static/index.html': change_html,
    'website/pilot_static/pilot.js': change_js,
    'website/pilot_static/pilot.css': change_css,
}


def main() -> int:
    # The CSS marker is written LAST. If it exists, the prior install reached
    # the end of the transaction, and repeat commands must not reapply anchors.
    marker_file = SITE / 'pilot_static' / 'pilot.css'
    if marker_file.is_file() and VERSION_TAG in marker_file.read_text(encoding='utf-8'):
        print('PASS：此版本已安裝，不重複修改。')
        return 0
    # Strict all-or-nothing preflight. Do not modify unknown versions.
    before = {}
    after = {}
    for relative, modify in FILES.items():
        path = ROOT / relative
        if not path.is_file():
            raise ValueError(f'找不到程式檔：{relative}')
        old = path.read_text(encoding='utf-8')
        before[path] = old
        after[path] = modify(old)
        if path.suffix == '.py':
            ast.parse(after[path], filename=relative)
        if relative.endswith('.js') and shutil.which('node'):
            check = subprocess.run(['node', '--check'], input=after[path],
                                   text=True, capture_output=True)
            if check.returncode:
                raise ValueError('修改後的 JavaScript 語法檢查未通過；未修改檔案')

    root_backup = ROOT / 'backups' / ('clinic_admin_fix_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
    for path, raw in before.items():
        dest = root_backup / path.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(raw, encoding='utf-8')
    print('備份資料夾：', root_backup)

    written = []
    try:
        for path, changed in after.items():
            with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent,
                                             prefix='.clinic-fix-', delete=False) as tmp:
                temp_path = Path(tmp.name)
                tmp.write(changed)
            temp_path.chmod(path.stat().st_mode & 0o777)
            temp_path.replace(path)
            written.append(path)
            print('PASS:', path.relative_to(ROOT))
    except Exception:
        for path in written:
            path.write_text(before[path], encoding='utf-8')
        print('失敗：已回復原檔案；備份仍保留', file=sys.stderr)
        raise
    print('PASS：登入路由、錯誤處理與 Firebase 狀態文案修正完成')
    print('請執行：./.venv/bin/python -m pytest -q tests')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        raise SystemExit('STOP：' + str(exc))
