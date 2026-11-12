"""Phase 7: fail-closed, clinic-aware navigation for the LOCAL 8006 preview.

A clinic query parameter is not a database tenant identifier. The original
booking backend does not accept a clinic identifier, so this module NEVER
claims the original endpoints are tenant-isolated or permits final bookings.
Shanlin is presented read-only. Yidian retains the previously tested local
self-pay and Taigi UI, but only with deliberately empty preview clinic slots.
Original site, clinic.js, Firebase, and PILOT records remain unchanged.
"""
from __future__ import annotations

from pathlib import Path
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from integrated_booking_page import make_checked_booking_html
from integrated_site import home_page as original_home_page

SITE = Path(__file__).resolve().parent
router = APIRouter()
LOCAL_CLIENTS = frozenset({'127.0.0.1', '::1', 'localhost', 'testclient'})
CLINICS = {'yidian': '頤典診所', 'shanlin': '山林診所'}
HEADERS = {
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer',
}


def local_only(request: Request) -> None:
    if not request.client or request.client.host not in LOCAL_CLIENTS:
        raise HTTPException(403, '此本機整合展示頁僅允許從本機存取')


def valid_clinic(clinic: str | None, *, default: str = 'yidian') -> str:
    name = clinic if clinic is not None else default
    if name not in CLINICS:
        raise HTTPException(404, '不支援的診所識別碼')
    return name


def preview_config() -> dict:
    """Neutral Yidian preview fields, not an assertion of real availability."""
    return {
        'name': '頤典診所',
        'phone': '', 'address': '', 'addressNote': '', 'hours': '',
        'elderlyDates': [], 'elderlyTimes': [],
        'selfPayWeekly': {day: [] for day in ('sun','mon','tue','wed','thu','fri','sat')},
        'selfPaySessions': {
            'morning': '08:30-12:30',
            'afternoon': '13:30-17:30',
            'evening': '18:30-21:00',
        },
        'closedDates': [], 'selfPayDailyLimit': 0, 'elderlyDailyLimit': 0,
    }


def clinic_profile(clinic: str) -> dict:
    slug = valid_clinic(clinic)
    return {
        'clinicId': slug,
        'name': CLINICS[slug],
        'mode': 'local_read_only_preview',
        'verifiedContactAvailable': False,
        'verifiedScheduleAvailable': False,
        'verifiedPhysiciansAvailable': False,
        'bookingEnabled': False,
        'backendIsolationVerified': False,
        'catalogPublishedForBooking': False,
        'notice': '此為本機整合展示；診所個別資料庫、時段及正式預約 API 尚未核對與開通。',
    }


STYLE = """
:root { color-scheme: light; --ink:#183b4f; --blue:#8baebe; --deep:#37657b; --border:#c5dce7; --pale:#f2f8fa; }
* { box-sizing:border-box; }
body { margin:0; font-family:-apple-system,BlinkMacSystemFont,'Noto Sans TC','PingFang TC',system-ui,sans-serif; color:var(--ink); background:#f8fbfc; }
header { background:var(--blue); padding:20px max(20px,calc((100vw - 1020px)/2)); display:flex; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap; }
.brand { font-weight:800; font-size:21px; text-decoration:none; color:#12384d; }
nav { display:flex; gap:10px; flex-wrap:wrap; }
nav a { color:#193f56; text-decoration:none; font-weight:650; padding:9px 12px; background:rgba(255,255,255,.65); border-radius:10px; }
main { max-width:1020px; margin:0 auto; padding:46px 20px 80px; }
h1 { margin:6px 0 12px; font-size:clamp(30px,4.5vw,48px); letter-spacing:.015em; }
p { line-height:1.85; }
.lead { font-size:18px; color:#527184; }
.cards { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:22px; margin-top:26px; }
.card { background:white; border:1px solid var(--border); border-radius:19px; padding:25px; box-shadow:0 4px 20px rgba(38,72,92,.06); }
.card h2 { font-size:25px; margin:4px 0 10px; }
.pill { display:inline-block; color:#406177; font-size:13px; font-weight:700; background:var(--pale); border-radius:99px; padding:5px 11px; }
.actions { display:flex; gap:12px; flex-wrap:wrap; margin-top:22px; }
.action { text-decoration:none; display:inline-block; padding:12px 18px; border-radius:10px; border:2px solid var(--deep); font-weight:750; background:var(--deep); color:white; }
.action.secondary { background:white; color:var(--deep); }
.notice { padding:18px 20px; border:1px solid var(--border); border-radius:14px; background:#f1f7fa; margin-top:24px; }
.notice strong { display:block; margin-bottom:4px; }
.small { font-size:14px; color:#577181; }
@media(max-width:700px){ .cards{grid-template-columns:1fr;} main{padding-top:26px;} }
"""


def _shell(title: str, body: str) -> HTMLResponse:
    html = (
        '<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{title}｜頤典雙診所整合展示</title>'
        f'<style>{STYLE}</style></head><body>'
        '<header><a class="brand" href="/clinics">頤典 DOUBTS · 雙診所本機展示</a>'
        '<nav aria-label="切換診所"><a href="/clinics">選擇診所</a>'
        '<a href="/appointment2.html?clinic=yidian&amp;p=SELF_PAY&amp;directSelfPay=1">頤典診所</a>'
        '<a href="/appointment2.html?clinic=shanlin&amp;p=SELF_PAY&amp;directSelfPay=1">山林診所</a></nav></header>'
        f'<main>{body}</main></body></html>'
    )
    return HTMLResponse(html, headers={**HEADERS, 'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"})


def chooser_page() -> HTMLResponse:
    return _shell('選擇診所', '''
<h1>請選擇診所</h1>
<p class="lead">同一個 8006 本機程式入口；兩家診所分別辨識。正式資料庫及預約尚未隔離完成，這裡不接受真實預約。</p>
<section class="cards" aria-label="診所選擇">
  <article class="card"><span class="pill">yidian · 預約功能展示</span><h2>頤典診所</h2>
    <p>沿用已測試的自費健檢項目、價格比對、國語與台語語音助理。預約送出已停用，日期與醫師資料未核對。</p>
    <div class="actions"><a class="action" href="/appointment2.html?clinic=yidian&amp;p=SELF_PAY&amp;directSelfPay=1">進入頤典展示</a></div></article>
  <article class="card"><span class="pill">shanlin · 唯讀展示</span><h2>山林診所</h2>
    <p>目前只提供診所辨識及公版入口；沒有核准可用的專屬預約 API、醫師時段或獨立病患資料寫入路徑。</p>
    <div class="actions"><a class="action" href="/appointment2.html?clinic=shanlin&amp;p=SELF_PAY&amp;directSelfPay=1">進入山林展示</a>
    <a class="action secondary" href="/pilot?clinic=shanlin">查看公版入口</a></div></article>
</section>
<div class="notice"><strong>本機安全展示</strong>請勿填寫姓名、身分證字號或其他真實病患資料；正式預約 API 在此階段已停用。</div>
''')


def shanlin_preview() -> HTMLResponse:
    # Deliberately does NOT embed appointment2.html, self_pay API, legacy clinic.js,
    # old booking backend, or any HTML form accepting personal details.
    return _shell('山林診所', '''
<span class="pill">shanlin · 資料隔離保護中</span>
<h1>山林診所</h1>
<p class="lead">已從網址識別為山林診所，而非頤典診所。</p>
<div class="notice"><strong>尚未開放正式預約</strong>
目前原預約 API 尚未帶有診所識別碼，無法證實山林有獨立的醫師時段、價格發布版本和病患資料庫。為避免兩家診所資料混用，這個頁面只提供唯讀展示，不收集病患資料、也不能送出預約。</div>
<section class="cards" aria-label="展示資訊">
  <article class="card"><h2>診所設定與管理</h2><p>可進入已建立的公版展示入口，核對診所資料。未核准的草稿不會自動發布。</p>
  <div class="actions"><a class="action" href="/pilot?clinic=shanlin">山林公版入口</a></div></article>
  <article class="card"><h2>正式預約前尚需完成</h2>
  <p>核對診所身份與聯絡資訊、建立獨立預約資料庫、設定醫師與時段、確認健檢價格及正式發布版本，再進行端到端預約驗收。</p>
  <p class="small">目前未提供經核實的電話、地址、醫師或時段；不會套用頤典資料。</p></article>
</section>
''')


def yidian_booking_html() -> HTMLResponse:
    try:
        source = (SITE / 'appointment2.html').read_text(encoding='utf-8')
        checked = make_checked_booking_html(source)
    except (OSError, ValueError) as exc:
        raise HTTPException(503, '預約頁面版本變更，暫停整合展示') from exc
    anchor = '<main id="main">'
    if checked.count(anchor) != 1:
        raise HTTPException(503, '預約頁面主區塊格式變更')
    warning = '''<div id="integrated-clinic-warning" role="status" style="padding:13px 22px;background:#f2f8fa;border-bottom:2px solid #8baebe;color:#224559;font-weight:650">
      頤典診所 · 8006 本機展示：僅供自費項目與台語功能測試；診所時段及預約資料庫尚未隔離核定，請勿輸入真實病患資料，也不能送出正式預約。
      <a href="/clinics" style="margin-left:10px;color:#234e69;text-decoration:underline">切換診所</a>
    </div>'''
    checked = checked.replace(anchor, warning + '\n' + anchor, 1)
    # Guard against a legacy clinic.js rewriting a clinic name loaded from a
    # shared backend. This changes visible identity ONLY, never medical data.
    identity_script = '''<script id="integrated-clinic-identity">
(function(){'use strict';
  const displayName='頤典診所';
  function apply(){
    document.querySelectorAll('[data-clinic="name"]').forEach(function(el){
      if(el.textContent!==displayName)el.textContent=displayName;
    });
    if(document.title!=='填寫基本資料 - 頤典診所（本機展示）') document.title='填寫基本資料 - 頤典診所（本機展示）';
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',apply);
  else apply();
  const obs=new MutationObserver(apply);
  obs.observe(document.documentElement,{subtree:true,childList:true,characterData:true});
})();
</script>'''
    if checked.count('</body>') != 1:
        raise HTTPException(503, '預約頁面主體格式變更')
    checked = checked.replace('</body>', identity_script + '\n</body>', 1)
    return HTMLResponse(checked, headers=HEADERS)


@router.get('/clinics', include_in_schema=False)
def clinic_chooser(request: Request):
    local_only(request)
    return chooser_page()


@router.get('/clinics/{clinic}', include_in_schema=False)
def clinic_entry(clinic: str, request: Request):
    local_only(request)
    slug = valid_clinic(clinic)
    if slug == 'shanlin':
        return shanlin_preview()
    return RedirectResponse('/appointment2.html?clinic=yidian&p=SELF_PAY&directSelfPay=1', status_code=303, headers=HEADERS)


@router.get('/api/integrated/clinics', include_in_schema=False)
def list_clinics(request: Request):
    local_only(request)
    return JSONResponse({'clinics': [clinic_profile(k) for k in CLINICS], 'mode': 'local_preview'}, headers=HEADERS)


@router.get('/api/integrated/clinics/{clinic}/public', include_in_schema=False)
def public_clinic_profile(clinic: str, request: Request):
    local_only(request)
    return JSONResponse(clinic_profile(clinic), headers=HEADERS)


@router.get('/', include_in_schema=False)
@router.get('/index.html', include_in_schema=False)
def clinic_home(request: Request, clinic: str | None = None):
    local_only(request)
    if clinic is None or valid_clinic(clinic) == 'yidian':
        # Keep the original voice home page, but show which clinic is selected.
        original = original_home_page()
        html = original.body.decode('utf-8')
        switcher = ('<div id="integrated-clinic-switcher" role="status" '
            'style="background:#e6f2f7;padding:12px 20px;text-align:center;'
            'font-weight:700;color:#24475c">'
            '目前為頤典診所本機展示，正式預約尚未開放。'
            '<a href="/clinics" style="color:#224a6a;text-decoration:underline;'
            'margin-left:12px">切換診所</a></div>')
        html, count = re.subn(r'(<body\b[^>]*>)', lambda m: m.group(1)+switcher,
                              html, count=1, flags=re.I)
        if count != 1:
            raise HTTPException(503, '原首頁版本變更，暫停診所切換展示')
        return HTMLResponse(html, headers=HEADERS)
    return shanlin_preview()


@router.get('/appointment2.html', include_in_schema=False)
def clinic_booking_entry(request: Request, clinic: str | None = None):
    local_only(request)
    if valid_clinic(clinic) == 'shanlin':
        return shanlin_preview()
    return yidian_booking_html()


@router.get('/api/clinic-config', include_in_schema=False)
def isolated_preview_clinic_config(request: Request, clinic: str | None = None):
    local_only(request)
    if valid_clinic(clinic) != 'yidian':
        raise HTTPException(423, '山林尚未接入獨立預約設定')
    return JSONResponse({'status': 'success', 'clinicId': 'yidian',
                         'previewOnly': True, 'clinic': preview_config()}, headers=HEADERS)


@router.get('/api/availability', include_in_schema=False)
def isolated_preview_availability(request: Request, clinic: str | None = None):
    local_only(request)
    if valid_clinic(clinic) != 'yidian':
        raise HTTPException(423, '山林尚未接入獨立名額資料')
    # Never read the shared legacy Firebase appointments table for the preview.
    return JSONResponse({'status': 'success', 'previewOnly': True,
                         'elderly': {}, 'selfPay': {}}, headers=HEADERS)


@router.get('/api/questions', include_in_schema=False)
def isolated_preview_questions(request: Request, clinic: str | None = None, mode: str = ''):
    local_only(request)
    if valid_clinic(clinic) != 'yidian':
        raise HTTPException(423, '山林尚未接入獨立問診設定')
    # The original questions endpoint uses a shared booking_config/questions path.
    return JSONResponse({'status': 'success', 'previewOnly': True,
                         'questions': []}, headers=HEADERS)
