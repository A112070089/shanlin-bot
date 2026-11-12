"""Phase 7B: HOME-first clinic identity for the LOCAL 8006 preview.

Every clinic identity is chosen at the initial homepage, not in a later form.
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


def _shell(title: str, body: str, clinic: str | None = None) -> HTMLResponse:
    brand = CLINICS[clinic] if clinic in CLINICS else '頤典 DOUBTS · 本機雙診所展示'
    html = (
        '<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{title}｜本機展示</title>'
        f'<style>{STYLE}</style></head><body>'
        f'<header><span class="brand">{brand}</span></header>'
        f'<main>{body}</main></body></html>'
    )
    return HTMLResponse(html, headers={**HEADERS, 'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"})


def chooser_page() -> HTMLResponse:
    return _shell('選擇診所', '''
<h1>請選擇診所</h1>
<p class="lead">這是開發者專用的兩個網站起點，不是預約中途的切換功能。進入哪家診所首頁，後續流程就沿用同一診所身分。正式資料庫及預約尚未隔離完成，這裡不接受真實預約。</p>
<section class="cards" aria-label="診所選擇">
  <article class="card"><span class="pill">yidian · 預約功能展示</span><h2>頤典診所</h2>
    <p>沿用已測試的自費健檢項目、價格比對、國語與台語語音助理。預約送出已停用，日期與醫師資料未核對。</p>
    <div class="actions"><a class="action" href="/?clinic=yidian">從頤典首頁開始</a></div></article>
  <article class="card"><span class="pill">shanlin · 唯讀展示</span><h2>山林診所</h2>
    <p>目前只提供診所辨識及公版入口；沒有核准可用的專屬預約 API、醫師時段或獨立病患資料寫入路徑。</p>
    <div class="actions"><a class="action" href="/?clinic=shanlin">從山林首頁開始</a>
    <a class="action secondary" href="/pilot?clinic=shanlin">查看公版入口</a></div></article>
</section>
<div class="notice"><strong>本機安全展示</strong>請勿填寫姓名、身分證字號或其他真實病患資料；正式預約 API 在此階段已停用。</div>
''')


def _replace_once(text: str, old: str, new: str, part: str) -> str:
    '''Fail closed when the real homepage has changed since review.'''
    if text.count(old) != 1:
        raise HTTPException(503, f'共用首頁版型的{part}已更新，暫停山林展示以免資訊錯置')
    return text.replace(old, new, 1)


def _replace_pattern_once(text: str, pattern: str, new: str, part: str) -> str:
    updated, count = re.subn(pattern, lambda _match: new, text, count=1, flags=re.I | re.S)
    if count != 1:
        raise HTTPException(503, f'共用首頁版型的{part}已更新，暫停山林展示以免資訊錯置')
    return updated


def shanlin_preview() -> HTMLResponse:
    '''Render Shanlin using THE SAME original index.html layout as Yidian.

    This is deliberately static: no patient fields, Yidian schedule/catalog,
    old clinic.js, AI/booking scripts, or booking requests. We retain the real
    header / hero / step / plan-card / footer CSS and DOM layout classes.
    The Yidian source HTML remains unchanged on disk.
    '''
    source = original_home_page().body.decode('utf-8')
    required_markers = (
        '</head>', '<header id="header"', '<main id="main">',
        '<footer class="footer">', '<section id="scrollspyHero"',
        '<section id="scrollspyAppointment"',
    )
    if any(source.count(m) != 1 for m in required_markers):
        raise HTTPException(503, '原首頁結構已更新，暫停山林展示')

    # Copy the original head, so the actual typography, CSS and responsive
    # breakpoints are identical. Never carry over the active home-page JS.
    head = source[:source.index('</head>') + len('</head>')]
    head = _replace_once(head, '<title>診所智慧預約助理 頤典</title>',
                         '<title>山林診所｜本機展示</title>', '網頁標題')
    head = _replace_pattern_once(head, r'<meta\s+name="description"\s+content="[^"]*"\s*>',
                                 '<meta name="description" content="山林診所本機展示；正式預約及服務項目待診所核對。">', '描述')
    head = _replace_pattern_once(head, r'<meta\s+name="author"\s+content="[^"]*"\s*>',
                                 '<meta name="author" content="山林診所（本機展示）">', '作者資訊')
    head = _replace_pattern_once(head, r'<meta\s+name="keywords"\s+content="[^"]*"\s*>',
                                 '<meta name="keywords" content="山林診所,本機展示">', '搜尋關鍵字')
    head = re.sub(r'<script\b[^>]*>[\s\S]*?</script\s*>', '', head, flags=re.I)
    head = _replace_once(head, '</head>', '''<style id="shared-clinic-home-preview-style">
      /* Keep the existing design, make unavailable actions visibly inert. */
      .senior-hero-actions-v14 button[disabled],
      .elderly-plan-action[aria-disabled="true"] { opacity: .75; cursor: not-allowed; }
      .shared-home-notice { background: #e6f2f7; color: #24475c; padding: 12px 20px;
        font-weight: 700; text-align: center; }
      .shared-plan-pending { color: #4a6e81; }
    </style></head>''', '展示專用樣式')

    # Copy the *actual Yidian header markup*, not the older custom Shanlin shell.
    header_start = source.index('<header id="header"')
    header = source[header_start:source.index('</header>', header_start) + len('</header>')]
    header = _replace_once(header, '<span data-clinic="name">頤典診所</span>',
                           '<span data-clinic="name">山林診所</span>', '診所名稱')
    header = _replace_once(header, 'href="index.html"', 'href="/?clinic=shanlin"', '首頁導覽')
    header = _replace_once(header, 'href="appointment.html"', 'href="#scrollspyAppointment"', '預約導覽')
    header = _replace_once(header, 'href="#"\n    onclick="openSelfPayBrowser(); return false;"',
                           'href="#scrollspyAppointment"', '自費導覽')
    header = _replace_once(header, 'href="https://a112070089.github.io/shanlin-bot/admin.html"',
                           'href="/pilot?clinic=shanlin&amp;view=admin"', '公版入口')
    header = _replace_once(header, '<img src="./assets/img/branding/logo.png" class="bsb-tpl-logo" alt="">',
                           '', '品牌圖樣')

    # The original main is reused, with unverified medical program content
    # changed to neutral placeholders. Do NOT suggest Taipei City's Yidian
    # elderly program or its prices are already approved for Shanlin.
    main_start = source.index('<main id="main">')
    main = source[main_start:source.index('</main>', main_start) + len('</main>')]
    main = _replace_once(main, 'aria-label="頤典 DOUBTS，科技讓醫療更有溫度"',
                         'aria-label="山林診所，本機展示"', '主視覺說明')
    main = _replace_once(main, '<span class="doubts-identity-name">頤典 <small>DOUBTS</small></span>',
                         '<span class="doubts-identity-name">山林 <small>診所</small></span>', '主視覺品牌')
    main = _replace_once(main, '115年臺北市<br />老人健康檢查',
                         '山林診所<br />健康檢查服務', '首頁主標題')
    action_marker = '<div class="d-grid gap-2 d-sm-flex flex-wrap mt-4 senior-hero-actions-v14">'
    if main.count(action_marker) != 1:
        raise HTTPException(503, '首頁三項服務按鈕結構已更新')
    a = main.index(action_marker)
    b = main.index('</div>', a) + len('</div>')
    main = main[:a] + '''<div class="d-grid gap-2 d-sm-flex flex-wrap mt-4 senior-hero-actions-v14">
      <button type="button" disabled aria-disabled="true" class="btn btn-primary bsb-btn-2xl rounded-pill"
        title="山林獨立預約尚未開通">一般預約</button>
      <button type="button" disabled aria-disabled="true"
        class="btn btn-outline-primary bsb-btn-2xl rounded-pill d-flex align-items-center justify-content-center"
        title="山林老人健檢內容尚未核定">老人健檢語音助理</button>
      <button type="button" disabled aria-disabled="true"
        class="btn btn-outline-primary bsb-btn-2xl rounded-pill d-flex align-items-center justify-content-center"
        title="山林自費檢查目錄尚未正式發布">自費加購語音助理</button>
    </div>''' + main[b:]
    main = _replace_once(main, '先了解三個步驟，再選擇健檢方案。',
                         '沿用相同的首頁設計；山林服務與預約仍待診所核准。', '健檢流程文字')

    steps_start = '<ol class="elderly-booking-steps" aria-label="健檢流程三步驟">'
    if main.count(steps_start) != 1:
        raise HTTPException(503, '首頁服務步驟結構已更新')
    a = main.index(steps_start)
    b = main.index('</ol>', a) + len('</ol>')
    step_info = (
        ('核對診所資料', '確認山林診所的聯絡資訊、服務項目與管理權限。'),
        ('核對健檢目錄', '由診所審核可提供的檢查項目、價格與適用資格。'),
        ('開通獨立預約', '建立山林專屬醫師時段、資料儲存與預約驗收後才開放。'),
    )
    steps = [steps_start]
    for index, (title, description) in enumerate(step_info, 1):
        steps.append(f'''<li class="elderly-booking-step">
          <span class="elderly-step-number" aria-hidden="true">{index}</span>
          <div class="elderly-step-content"><h3>{title}</h3><p>{description}</p></div>
        </li>''')
    steps.append('</ol>')
    main = main[:a] + '\n'.join(steps) + main[b:]
    main = _replace_once(main, '※ 受檢資格須由診所現場確認。',
                         '※ 山林診所的健檢內容及開放日期尚待核定。', '受檢資格說明')
    main = _replace_once(main, '先看主要項目；如需詳細資訊，可展開完整清單。',
                         '方案位置與設計沿用頤典版型，正式項目內容尚待山林診所核准。', '健檢目錄說明')

    grid_start = '<div class="elderly-plan-grid" aria-labelledby="elderlyPlansTitle">'
    grid_end_marker = '\n      </div>\n    </section>'
    if main.count(grid_start) != 1 or grid_end_marker not in main[main.index(grid_start):]:
        raise HTTPException(503, '首頁健檢方案版型已更新')
    a = main.index(grid_start)
    b = main.index(grid_end_marker, a)
    plans = [grid_start]
    for plan in ('A', 'B', 'C'):
        plans.append(f'''<article class="elderly-plan-card" aria-labelledby="elderlyPlan{plan}">
          <div class="elderly-plan-header"><span class="elderly-plan-code">{plan} 方案</span>
            <h3 id="elderlyPlan{plan}">方案待確認</h3></div>
          <p class="elderly-plan-preview-label">目前僅供展示</p>
          <ul class="elderly-plan-preview shared-plan-pending">
            <li>實際服務內容由山林診所核准後顯示</li>
            <li>價格與時段尚未發布</li>
          </ul>
          <span class="elderly-plan-action" aria-disabled="true">尚未開放預約</span>
        </article>''')
    plans.append('</div>')
    main = main[:a] + '\n'.join(plans) + main[b:]

    footer_start = source.index('<footer class="footer">')
    footer = source[footer_start:source.index('</footer>', footer_start) + len('</footer>')]
    footer = _replace_pattern_once(footer, r'<address class="mb-4" data-clinic="address">.*?</address>',
                                   '<address class="mb-4">山林診所地址待診所確認</address>', '聯絡地址')
    footer = _replace_pattern_once(footer, r'<p class="mb-4"><a[^>]*data-clinic="phone"[^>]*>.*?</a></p>',
                                   '<p class="mb-4">電話及服務時間待診所核對</p>', '聯絡電話')
    footer = _replace_pattern_once(footer, r'<div class="copyright[^>]*>.*?</div>',
                                   '<div class="copyright text-center text-md-start">山林診所 · 本機安全展示</div>',
                                   '頁尾版權')

    notice = ('''<div class="shared-home-notice" id="integrated-clinic-home-notice" role="status">
      山林診所 · 本機展示。頁面設計與頤典相同；正式健檢方案、聯絡資訊及預約功能尚未核准開放。
      請勿輸入真實個人資料。
    </div>''')
    html = (head + '\n<body>\n' + notice + '\n' + header + '\n' + main +
            '\n' + footer + '\n' +
            '<script defer src="https://unpkg.com/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>' +
            '\n</body>\n</html>')
    # This page does not include the source app's modal, input fields,
    # booking/AI scripts, or any API-capable JavaScript. Fail closed if a
    # future source markup unexpectedly leaks these into curated regions.
    forbidden = ('<form', '<input', 'onclick=', 'onpointer', 'site-config.js',
                 'clinic.js', 'yidian_speech.js', 'booking_questions.js',
                 '/api/booking', '/api/self_pay', 'login.php',
                 '臺北市文山區羅斯福路', '02 2933 2010',
                 '115年臺北市', '胸部X光', '甲狀腺刺激素')
    if any(term in html for term in forbidden):
        raise HTTPException(503, '共用首頁含未核准的舊診所資料，已暫停山林展示')
    csp = ("default-src 'none'; style-src 'self' 'unsafe-inline' "
           "https://fonts.googleapis.com https://cdn.jsdelivr.net; "
           "font-src 'self' https://fonts.gstatic.com data:; "
           "img-src 'self' data:; script-src https://unpkg.com; "
           "connect-src 'none'; form-action 'none'; object-src 'none'; "
           "base-uri 'none'; frame-ancestors 'none'")
    return HTMLResponse(html, headers={**HEADERS, 'Content-Security-Policy': csp})


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
      <a href="/?clinic=yidian" style="margin-left:10px;color:#234e69;text-decoration:underline">返回頤典首頁</a>
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
    # This legacy chooser route is now an ENTRY point, never a shortcut into a form.
    return RedirectResponse('/?clinic=' + slug, status_code=303, headers=HEADERS)


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
    slug = valid_clinic(clinic)
    if slug == 'shanlin':
        # This is the Shanlin HOMEPAGE, not a shared Yidian patient form.
        return shanlin_preview()

    original = original_home_page()
    html = original.body.decode('utf-8')
    # Carry the homepage clinic identity into the pre-existing self-pay step.
    # This exact link is executed AFTER the homepage confirms basic details.
    old = '"appointment2.html?p=SELF_PAY&directSelfPay=1";'
    new = '"appointment2.html?clinic=yidian&p=SELF_PAY&directSelfPay=1";'
    if html.count(old) != 1:
        raise HTTPException(503, '首頁自費健檢跳轉規則已改變，暫停整合展示')
    html = html.replace(old, new, 1)
    # Store clinic identity with the existing homepage-to-appointment handoff.
    # Neither this client value nor a URL parameter authorizes server-side writes.
    marker = ('sessionStorage.setItem(\n'
              '    "directSelfPayBasicData",\n'
              '    JSON.stringify({')
    if html.count(marker) != 1:
        raise HTTPException(503, '首頁病患流程交接格式已改變，暫停整合展示')
    a = html.index(marker)
    b = html.index('  // 前往 appointment2.html', a)
    block = html[a:b]
    old_birth = '      birthday: bookingData.birthday || ""'
    if block.count(old_birth) != 1:
        raise HTTPException(503, '首頁資料交接欄位格式已改變，暫停整合展示')
    block = block.replace(old_birth,
                          '      birthday: bookingData.birthday || "",\n'
                          '      clinicId: "yidian"', 1)
    html = html[:a] + block + html[b:]

    # A simple header notice, not a clinic switcher in the middle of booking.
    notice = ('<div id="integrated-clinic-home-notice" role="status" '
              'style="background:#e6f2f7;padding:12px 20px;text-align:center;'
              'font-weight:700;color:#24475c">'
              '頤典診所 · 本機展示。尚未開放正式預約，請勿使用真實病患資料。'
              '</div>')
    html, count = re.subn(r'(<body\b[^>]*>)', lambda m: m.group(1) + notice,
                          html, count=1, flags=re.I)
    if count != 1:
        raise HTTPException(503, '原首頁版本變更，暫停診所首頁展示')
    return HTMLResponse(html, headers=HEADERS)


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
