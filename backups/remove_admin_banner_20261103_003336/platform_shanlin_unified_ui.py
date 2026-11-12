"""Opt-in same-page Shanlin staff UI overlay for the existing 8019 test server.

Does not touch production or modify the original website files.
Transforms only the existing local templates while preserving the tested
booking-stage API and authentic clinic-admin session.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _replace_once(html: str, old: str, new: str, where: str) -> str:
    if html.count(old) != 1:
        raise RuntimeError(f"BLOCKED: {where} source changed; expected one exact anchor, found {html.count(old)}")
    return html.replace(old, new, 1)


def unified_index() -> str:
    html = (HERE / 'pilot_static' / 'index.html').read_text(encoding='utf-8')
    html = _replace_once(
        html,
        '<a class="outline-button" href="https://shanlin-bot-production.up.railway.app/admin.html" target="_blank" rel="noopener noreferrer">開啟山林正式管理後台 ↗</a>',
        '<p class="small-note">此頁僅顯示已驗證的正式診所基本資料快照；正式修改尚未整合到測試公版。請勿把測試資料寫入正式系統。</p>',
        'original external config link',
    )
    html = _replace_once(
        html,
        '<div class="form-footer"><a href="http://127.0.0.1:5500/admin.html" target="_blank" rel="noopener noreferrer" class="primary-button" id="openLegacyAdmin" hidden>開啟山林預約管理系統</a><button type="button" id="refreshIntegrationBtn" class="outline-button">重新整理</button></div>',
        '<div class="form-footer" id="appointmentLegacyActions"><button type="button" id="openLegacyAdmin" hidden style="display:none!important" aria-hidden="true" tabindex="-1"></button><button type="button" id="refreshIntegrationBtn" class="outline-button">重新整理</button></div>\n'
        '      <div id="shanlinUnifiedBookings" hidden>\n'
        '        <p class="unified-test-note">僅供山林診所合成資料交易驗證｜使用獨立測試 Firebase｜不發送 LINE 提醒｜尚未完成正式驗收</p>\n'
        '        <iframe id="shanlinBookingFrame" title="山林診所預約管理（測試資料）" loading="lazy" referrerpolicy="no-referrer" style="width:100%;height:1150px;border:0;display:block;background:#fff" ></iframe>\n'
        '      </div>',
        'original external appointment link',
    )
    return html


def unified_script() -> str:
    script = (HERE / 'pilot_static' / 'pilot.js').read_text(encoding='utf-8')
    script = _replace_once(
        script,
        "      const section=$(n+'Pane');if(section)section.hidden=n!==pane;",
        "      const section=$(n+'Pane');if(section)section.hidden=n!==pane;",
        'tabs are available',
    )
    script = _replace_once(
        script,
        "    currentPane=pane;\n    if(pane==='catalog'",
        "    currentPane=pane;\n"
        "    const embedded=clinic==='shanlin' && pane==='appointments';\n"
        "    $('shanlinUnifiedBookings').hidden=!embedded;\n"
        "    $('appointmentIntegration').hidden=embedded;\n"
        "    $('appointmentLegacyActions').hidden=embedded;\n"
        "    if(embedded){\n"
        "      const frame=$('shanlinBookingFrame');\n"
        "      if(!frame.getAttribute('src')){\n"
        "        frame.addEventListener('load',()=>{\n"
        "          try{\n"
        "            if(frame.contentWindow.location.origin!==location.origin)return;\n"
        "            const doc=frame.contentDocument;\n"
        "            const size=()=>{const h=doc.body.scrollHeight;frame.style.height=Math.max(900,Math.min(h+28,2400))+'px';};\n"
        "            size();new ResizeObserver(size).observe(doc.body);\n"
        "          }catch(_){}\n"
        "        },{once:true});\n"
        "        frame.setAttribute('src','/api/pilot/admin/shanlin/booking-frame');\n"
        "      }\n"
        "    }\n"
        "    if(pane==='catalog'",
        'tab integration',
    )
    script = _replace_once(
        script,
        "        ? '山林診所的基本資料與預約由既有管理系統維護；此處可管理科別、醫師及自費健檢目錄。'",
        "        ? '同一個管理後台提供診所資料、科別醫師、自費健檢目錄及測試預約管理。'",
        'admin intro',
    )
    script = _replace_once(
        script,
        "        ? '此處的診所基本資料僅供查看；如需修改，請使用山林正式管理後台。科別與醫師可在本系統另行管理。'",
        "        ? '正式診所基本資料目前僅供查看；變更權限與正式儲存流程尚未接入此測試系統。'",
        'read-only clinic note',
    )
    script = _replace_once(
        script,
        "          ? '已從山林診所正式後台取得基本資料；如需修改，請使用下方「開啟山林正式管理後台」。'",
        "          ? '已從山林正式來源取得基本資料（唯讀）；正式編輯功能尚未開放。'",
        'verified clinic snapshot note',
    )
    return script


def unified_css() -> str:
    css = (HERE / 'pilot_static' / 'pilot.css').read_text(encoding='utf-8')
    return css + '''\n/* Shanlin staff console: the existing DOUBTS #8BA8BA design system. */
#adminView:has(#shanlinUnifiedBookings:not([hidden])) .admin-subnav{background:#e9f2f6}
#adminView .unified-test-note{font-size:13px;line-height:1.7;color:#715727;background:#fff3d5;border:1px solid #ecd8ad;padding:10px 14px;border-radius:9px;margin:2px 0 16px}
#appointmentsPane:has(#shanlinUnifiedBookings:not([hidden])){padding:18px 18px 24px}
#appointmentsPane:has(#shanlinUnifiedBookings:not([hidden]))>.panel-head{margin-bottom:13px}
#shanlinBookingFrame{display:block;border:0;max-width:100%;border-radius:10px}
#shanlinUnifiedBookings[hidden]{display:none!important}
@media(max-width:700px){#appointmentsPane:has(#shanlinUnifiedBookings:not([hidden])){padding:12px 7px}}
'''


def unified_frame() -> str:
    source = (HERE / 'shanlin_admin_booking_stage.html').read_text(encoding='utf-8')
    # Reuse the installed capacity-message fix. Never silently revert its guard.
    if 'const reason = typeof error.detail' not in source:
        raise RuntimeError('BLOCKED: capacity-error UI fix missing from installed staging page')
    source = _replace_once(source, '<body>', '<body class="unified-embedded">', 'frame body')
    source = _replace_once(source,
      '<div style="background:#fff3cc;color:#654200;padding:12px;text-align:center;font-weight:700">僅供山林診所合成資料交易測試｜不連線正式 Firebase、不發送 LINE 提醒｜未完成正式驗收</div>',
      '', 'redundant test warning (shown by parent)')
    source = _replace_once(source, '<title>山林診所 預約管理後台</title>',
      '<title>山林診所｜預約管理</title>', 'frame title')
    source = _replace_once(source, '</style>', '''
/* Embedded same-origin clinic booking pane: no second masthead, login or nav. */
.unified-embedded{--ink:#1c3647;--ink-soft:#587080;--paper:#f5f8fa;--paper-deep:#e9f2f6;
--pine:#365c73;--pine-d:#29495e;--pine-l:#e1ecf2;--rust:#b36a3f;--rust-l:#faebdf;
--border:#cbdde6;--danger:#b23938;--danger-l:#fde9e7;min-height:0;background:#fff}
.unified-embedded .topbar{display:none}
.unified-embedded .shell{min-height:0}
.unified-embedded .main{padding:0 0 12px;max-width:none;min-height:0}
.unified-embedded .stats-row,.unified-embedded .search-bar,.unified-embedded .table-wrap{border-radius:10px}
.unified-embedded .page-head{margin-top:0}
.unified-embedded .modal-ov{align-items:flex-start;overflow-y:auto;padding-top:24px}
.unified-embedded .table-wrap{overflow-x:auto}
.unified-embedded #apptTable{min-width:1030px}
.unified-embedded .toast{top:18px;bottom:auto}
</style>''', 'frame palette')
    source = _replace_once(source, '<div class="modal-title">刪除預約紀錄</div>',
      '<div class="modal-title">取消預約</div>', 'cancel modal title')
    source = _replace_once(source, '確定要刪除 <strong id="deleteTargetName" style="color:var(--ink)">—</strong> 的預約紀錄嗎？此操作無法復原。',
      '確定要取消 <strong id="deleteTargetName" style="color:var(--ink)">—</strong> 的預約嗎？取消後會釋出名額，並保留原預約紀錄。', 'cancel modal description')
    source = _replace_once(source, 'onclick="confirmDelete()">確定刪除</button>',
      'onclick="confirmDelete()">確認取消預約</button>', 'cancel modal action')
    source = _replace_once(source, "showToast('已刪除預約紀錄');", "showToast('預約已取消，名額已釋出');", 'cancel success toast')
    source = _replace_once(source, "showToast('刪除失敗', true);", "showToast('取消失敗，請重新載入再試', true);", 'cancel error toast')
    # Correct local calendar week and exclude cancelled records from current activity.
    source = _replace_once(source, '''  const today = new Date().toISOString().split('T')[0];
  const weekStart = new Date(); weekStart.setDate(weekStart.getDate() - weekStart.getDay());
  const weekStr = weekStart.toISOString().split('T')[0];
  const todayCount = allAppts.filter(a => a.date === today).length;
  const weekCount = allAppts.filter(a => a.date >= weekStr).length;''',
    '''  const dtf=new Intl.DateTimeFormat('en-US',{timeZone:'Asia/Taipei',year:'numeric',month:'2-digit',day:'2-digit'});
  const taipeiDate=d=>{const p=Object.fromEntries(dtf.formatToParts(d).map(x=>[x.type,x.value]));return `${p.year}-${p.month}-${p.day}`;};
  const today=taipeiDate(new Date());
  const start=new Date(`${today}T12:00:00+08:00`);
  const weekday=(start.getUTCDay()+6)%7; // Monday = 0
  const monday=taipeiDate(new Date(start.getTime()-weekday*86400000));
  const sunday=taipeiDate(new Date(start.getTime()+(6-weekday)*86400000));
  const active=a=>a.cancelled!==true && a.status!=='cancelled';
  const todayCount=allAppts.filter(a=>active(a)&&a.date===today).length;
  const weekCount=allAppts.filter(a=>active(a)&&a.date>=monday&&a.date<=sunday).length;''',
      'today/weekly stats')
    return source
