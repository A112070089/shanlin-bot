"""Non-destructive local two-clinic home UI, built from the ORIGINAL index.html.

Shanlin reuses the existing genuine homepage, A/B/C elderly cards, footer,
voice dialogs and self-pay overlay. The 101/9 Shanlin source items stay in
self-pay APIs rather than being injected as a catalogue on the homepage.
Yidian keeps the exact same front-end sections but has no clinic catalogue.
Neither mode can submit a real booking through the integrated app.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import HTMLResponse

from integrated_booking_page import make_checked_booking_html

SITE = Path(__file__).resolve().parent
HEADERS = {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer'}


def once(text: str, original: str, replacement: str, label: str) -> str:
    if text.count(original) != 1:
        raise HTTPException(503, f'原首頁{label}結構已變動，未進行不完整的替換')
    return text.replace(original, replacement, 1)


def replace_region(text: str, start: str, stop: str, replacement: str, label: str) -> str:
    if text.count(start) != 1 or stop not in text[text.index(start):]:
        raise HTTPException(503, f'原首頁{label}結構已變動')
    i = text.index(start)
    j = text.index(stop, i)
    return text[:i] + replacement + text[j:]


# A browser-only tagging adapter: adds a clinic query to *read-only* APIs.
# Server middleware still validates clinic and rejects all booking writes.
# IMPORTANT: selecting a clinic in the browser does NOT authorize booking writes.
def scope_script(clinic: str) -> str:
    return '''<script id="integrated-home-clinic-scope">
(function () {
  'use strict';
  const clinic = ''' + json.dumps(clinic) + ''';
  try {
    const oldClinic = sessionStorage.getItem('integrated_home_clinic');
    if (oldClinic && oldClinic !== clinic) {
      sessionStorage.removeItem('directSelfPayBasicData');
      sessionStorage.removeItem('lastBooking');
    }
    sessionStorage.setItem('integrated_home_clinic', clinic);
  } catch (_) { /* Storage can be disabled: never block the UI. */ }
  window.INTEGRATED_CLINIC_ID = clinic;
  const nativeFetch = window.fetch.bind(window);
  const roots = ['/api/self_pay', '/api/clinic-config', '/api/availability',
                 '/api/questions', '/api/integrated/catalog'];
  window.fetch = function (input, init) {
    try {
      const locationStr = typeof input === 'string' || input instanceof URL ? String(input) : input.url;
      const dest = new URL(locationStr, window.location.href);
      if (dest.origin === window.location.origin &&
          roots.some(x => dest.pathname === x || dest.pathname.startsWith(x + '/'))) {
        dest.searchParams.set('clinic', clinic);
        const next = input instanceof Request ? new Request(dest.toString(), input) : dest.toString();
        return nativeFetch(next, init);
      }
    } catch (e) { console.warn('診所讀取 API 標記失敗', e); }
    return nativeFetch(input, init);
  };
})();
</script>'''


def base_source() -> str:
    # The existing source files are never overwritten.
    source = SITE / 'index.html'
    if not source.is_file():
        raise HTTPException(503, '找不到原始首頁 index.html')
    data = source.read_text(encoding='utf-8')
    for required in ('<header id="header"', '<main id="main">',
                     '<h2 id="elderlyBookingTitle">預約健檢</h2>',
                     '<div class="elderly-plan-grid"', '<footer class="footer">',
                     '<address class="mb-4" data-clinic="address">'):
        if required not in data:
            raise HTTPException(503, '原始首頁結構與已審核版本不同，未動到原始檔')
    return data


def build_shanlin_home() -> HTMLResponse:
    """Keep the real homepage's content/steps/footer and actual click handlers."""
    html = base_source()
    html = once(html, '<span data-clinic="name">頤典診所</span>',
                '<span data-clinic="name">山林診所</span>', '診所名稱')
    # Same visual class; only the tenant's name changes.
    html = once(html, '<span class="doubts-identity-name">頤典 <small>DOUBTS</small></span>',
                '<span class="doubts-identity-name">山林 <small>診所</small></span>', '主視覺品牌')
    html = once(html, '<title>診所智慧預約助理 頤典</title>',
                '<title>山林診所｜健康檢查與預約</title>', '標題')
    html = once(html, 'href="index.html"', 'href="/?clinic=shanlin"', '首頁導覽')
    html = once(html, 'href="appointment.html"',
                'href="#scrollspyAppointment"', '預約導覽')
    html = once(html, 'href="https://a112070089.github.io/shanlin-bot/admin.html"',
                'href="/pilot?clinic=shanlin&amp;view=admin"', '管理後台')
    for plan in 'ABC':
        html = once(html, f'href="./appointment.html?p={plan}"',
                    f'href="./appointment.html?clinic=shanlin&amp;p={plan}"', f'{plan}方案連結')
    # Keep original in-page JS and read-only modal instead of deleting buttons.
    html = once(html, '"appointment2.html?p=SELF_PAY&directSelfPay=1";',
                '"appointment2.html?clinic=shanlin&p=SELF_PAY&directSelfPay=1";', '自費交接')
    html = html.replace('`./appointment.html` +', '`./appointment.html?clinic=shanlin` +')
    html = html.replace('`?p=${encodeURIComponent(bookingData.plan)}` +',
                        '`&p=${encodeURIComponent(bookingData.plan)}` +')
    html = once(html, '<script src="site-config.js"></script>',
                scope_script('shanlin') + '\n<script src="site-config.js"></script>', 'API資料來源')
    # Not a new marketing banner; retain the original exact footer including
    # street address/phone rather than inventing '待診所確認'.
    assert '臺北市文山區羅斯福路六段407號2樓' in html
    assert '02 2933 2010' in html
    assert '公版設定流程' not in html and '山林現有自費加購項目' not in html
    return HTMLResponse(html, headers={**HEADERS, 'X-Clinic-Id': 'shanlin'})


EMPTY_CARDS = '''<div class="elderly-plan-grid" aria-labelledby="elderlyPlansTitle">
{cards}
</div>'''


def build_yidian_home() -> HTMLResponse:
    """Exact old homepage visual composition, with EMPTY clinic-specific plans.

    No old JS/medical dialogue or real patient form is loaded into Yidian.
    The buttons are clickable and give brief feedback, rather than disabled.
    """
    source = base_source()
    head = source[:source.index('</head>') + len('</head>')]
    header_start = source.index('<header id="header"')
    header = source[header_start:source.index('</header>', header_start) + len('</header>')]
    main_start = source.index('<main id="main">')
    main = source[main_start:source.index('</main>', main_start) + len('</main>')]
    footer_start = source.index('<footer class="footer">')
    footer = source[footer_start:source.index('</footer>', footer_start) + len('</footer>')]

    head = once(head, '<title>診所智慧預約助理 頤典</title>',
                '<title>頤典 DOUBTS｜健康檢查</title>', '標題')
    # Preserve existing CSS files, mobile breakpoints, original navbar,
    # three actions, plan-section DOM and footer styling, no custom shell.
    head = re.sub(r'<script\b[^>]*>[\s\S]*?</script\s*>', '', head, flags=re.I)
    header = once(header, 'href="index.html"', 'href="/?clinic=yidian"', '首頁導覽')
    header = once(header, 'href="appointment.html"',
                  'href="#scrollspyAppointment"', '預約導覽')
    header = once(header, 'href="https://a112070089.github.io/shanlin-bot/admin.html"',
                  'href="/pilot?clinic=yidian&amp;view=admin"', '管理後台')
    header = once(header, 'onclick="openSelfPayBrowser(); return false;"',
                  'onclick="showEmptyClinicMessage(); return false;"', '自費導覽')
    # A neutral hero title is preferable to importing Shanlin elder campaigns.
    main = once(main, '115年臺北市<br />老人健康檢查',
                '健康檢查<br />預約服務', '首頁標題')
    main = once(main, 'onclick="document.getElementById(\'chat-widget\').classList.add(\'elderly-readable-v15\'); openChat()"',
                'onclick="showEmptyClinicMessage()"', '語音服務按鈕')
    main = once(main, 'onclick="openSelfPayChat()"',
                'onclick="showEmptyClinicMessage()"', '加購服務按鈕')
    # Do not replace the original '預約健檢' heading or steps with
    # '公版設定流程' or onboarding instructions.
    cards = []
    for n in range(1, 4):
        cards.append(f'''<article class="elderly-plan-card" data-template-slot="{n}">
          <div class="elderly-plan-header">
            <span class="elderly-plan-code">方案 {n}</span>
            <h3>尚未建立方案</h3>
          </div>
          <p class="elderly-plan-preview-label">主要項目</p>
          <ul class="elderly-plan-preview"><li>尚未設定</li></ul>
          <button type="button" class="elderly-plan-action" onclick="showEmptyClinicMessage()">查看方案</button>
        </article>''')
    main = replace_region(main, '<div class="elderly-plan-grid" aria-labelledby="elderlyPlansTitle">',
                          '\n      </div>\n    </section>',
                          EMPTY_CARDS.format(cards='\n'.join(cards)), '方案卡片')
    # The former footer values originate in the partner's original project.
    # Yidian blank template must not advertise those as its real contacts.
    footer = re.sub(r'<address class="mb-4" data-clinic="address">[^<]*</address>',
                    '<address class="mb-4">—</address>', footer, count=1)
    footer = re.sub(r'<p class="mb-4"><a[^>]*data-clinic="phone"[^>]*>.*?</a></p>',
                    '<p class="mb-4">—</p>', footer, count=1, flags=re.S)
    # No extra sections; button-feedback appears only if actually clicked.
    feedback = '''<div id="emptyClinicMessage" role="status" hidden
        style="position:fixed;z-index:2500;bottom:20px;left:50%;transform:translateX(-50%);
        background:#fff;border:1px solid #8baebe;border-radius:14px;padding:14px 20px;
        box-shadow:0 8px 25px #1233;max-width:90vw;text-align:center;">
        目前尚無可供預約的健檢方案或自費項目。
        <button type="button" onclick="this.parentElement.hidden=true" aria-label="關閉提示"
          style="margin-left:12px;border:0;background:#8baebe;border-radius:7px;padding:6px 12px">關閉</button>
      </div>
      <script>function showEmptyClinicMessage(){
        document.getElementById('emptyClinicMessage').hidden=false;
      }</script>'''
    html = head + '\n<body>\n' + header + '\n' + main + '\n' + footer + '\n' + feedback + '\n</body></html>'
    # Prove no Shanlin items or leaked data-processing JS.
    forbidden = ('腦肺方案', '腹部方案', '骨密肌力方案', '血脂肪檢查',
                 'site-config.js', 'clinic.js', 'booking_questions.js',
                 'self_pay_chat.js', 'directSelfPayBasicData', '/api/self_pay',
                 '/api/booking/confirm', '公版設定流程', '山林現有',
                 '臺北市文山區羅斯福路六段407號2樓', '02 2933 2010')
    if any(word in html for word in forbidden):
        raise HTTPException(503, '公版首頁含錯誤診所內容，已停止展示')
    return HTMLResponse(html, headers={**HEADERS, 'X-Clinic-Id': 'yidian',
                                       'Content-Security-Policy': "default-src 'none'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; font-src 'self' https://fonts.gstatic.com data:; img-src 'self' data:; script-src 'unsafe-inline' https://unpkg.com; connect-src 'none'; form-action 'none'; base-uri 'none'"})


def scoped_booking_preview(filename: str, clinic: str) -> HTMLResponse:
    """Serve existing Shanlin forms without writing or claiming tenant DB isolation."""
    if clinic != 'shanlin':
        raise HTTPException(423, '頤典公版尚未建立獨立預約資料，請由首頁瀏覽版型')
    path = SITE / filename
    if not path.is_file():
        raise HTTPException(503, f'原預約頁面 {filename} 尚未包含於本機專案')
    html = path.read_text(encoding='utf-8')
    if filename == 'appointment2.html':
        try:
            html = make_checked_booking_html(html)
        except ValueError as exc:
            raise HTTPException(503, '原自費預約頁版本與核對程式不一致') from exc
    # Scope all read-only catalog calls to the current clinic in the browser.
    html = once(html, '</head>', scope_script('shanlin') + '</head>', '預約頁診所識別')
    # Replace only visible clinic name. Actual public config route also returns
    # Shanlin's original project contact details instead of the Yidian default.
    html = html.replace('data-clinic="name">頤典診所', 'data-clinic="name">山林診所')
    html = html.replace('href="index.html"', 'href="/?clinic=shanlin"')
    html = html.replace('href="./index.html"', 'href="/?clinic=shanlin"')
    # No new PII forms: these are the original pages. The local test server
    # rejects /api/booking/confirm before any original handler is called.
    notice = '''<aside style="background:#fff7e6;color:#6b4200;padding:10px 18px;text-align:center;
      border-bottom:1px solid #ead89d;" role="note">本機展示，尚未接受正式預約。請勿輸入真實病患個資。</aside>'''
    # Insert after the body opening tag so the HTML remains structurally valid.
    html, count = re.subn(r'(<body\b[^>]*>)', lambda match: match.group(1) + notice,
                          html, count=1, flags=re.I)
    if count != 1:
        raise HTTPException(503, '預約頁 body 標記不存在')
    return HTMLResponse(html, headers={**HEADERS, 'X-Clinic-Id': 'shanlin'})
