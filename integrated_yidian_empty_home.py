"""Blank Yidian template homepage, derived only from the shared CSS/HTML frame.

Yidian is a demo template with NO clinic catalog, confirmed prices, service hours,
patients or real appointments. Never import or inspect Shanlin source data here.
"""
from __future__ import annotations

import re
from fastapi import HTTPException
from fastapi.responses import HTMLResponse


STYLE = '''
/* Match the real shared template while making empty placeholders obvious. */
.demo-notice {background:#e6f2f7;color:#24475c;padding:13px 20px;
  font-weight:700;text-align:center;line-height:1.65;}
.senior-hero-actions-v14 button[disabled] {opacity:.78;cursor:not-allowed;}
.elderly-plan-action[aria-disabled="true"] {cursor:not-allowed;opacity:.75;}
.demo-empty-text {color:#587488;font-weight:600;line-height:1.7;}
.demo-empty-preview {list-style:none;padding:0;margin:12px 0 18px;}
.demo-empty-preview li {border:1px dashed #b6d0dd;border-radius:10px;
  padding:14px;color:#557486;background:#f6fafc;}
'''

CSP = ("default-src 'none'; style-src 'self' 'unsafe-inline' "
       "https://fonts.googleapis.com https://cdn.jsdelivr.net; "
       "font-src 'self' https://fonts.gstatic.com data:; "
       "img-src 'self' data:; script-src https://unpkg.com; "
       "connect-src 'none'; form-action 'none'; object-src 'none'; "
       "base-uri 'none'; frame-ancestors 'none'")


def once(source: str, old: str, new: str, label: str) -> str:
    if source.count(old) != 1:
        raise HTTPException(503, '公版首頁' + label + '格式變更，為避免展示錯誤資料已暫停')
    return source.replace(old, new, 1)


def pattern_once(source: str, pattern: str, new: str, label: str) -> str:
    output, count = re.subn(pattern, lambda _: new, source, count=1, flags=re.I | re.S)
    if count != 1:
        raise HTTPException(503, '公版首頁' + label + '格式變更，為避免展示錯誤資料已暫停')
    return output


def region(source: str, begin: str, end: str) -> str:
    if source.count(begin) != 1 or end not in source[source.index(begin):]:
        raise HTTPException(503, '公版首頁原始區塊變更，暫停展示')
    a = source.index(begin)
    b = source.index(end, a) + len(end)
    return source[a:b]


def build_yidian_empty_home(source: str, headers: dict) -> HTMLResponse:
    """Build the same visual frame as Shanlin, but with ZERO clinic data.

    Retain the original CSS/header/hero/steps/plan-card/footer elements; never
    retain original patient forms, embedded scripts, clinical schemes or prices.
    """
    required_markers = (
        '</head>', '<header id="header"', '<main id="main">',
        '<footer class="footer">', '<section id="scrollspyHero"',
        '<section id="scrollspyAppointment"',
    )
    if any(source.count(marker) != 1 for marker in required_markers):
        raise HTTPException(503, '公版首頁結構已更新，為避免錯誤資料已停止展示')
    head = source[:source.index('</head>') + len('</head>')]
    head = once(head, '<title>診所智慧預約助理 頤典</title>',
                '<title>頤典 DOUBTS｜空白公版範例（尚未設定）</title>', '標題')
    head = pattern_once(head, r'<meta\s+name="description"\s+content="[^"]*"\s*>',
                        '<meta name="description" content="頤典 DOUBTS 空白公版範例：尚未新增診所資料、健檢方案及價格。">', '描述')
    head = pattern_once(head, r'<meta\s+name="author"\s+content="[^"]*"\s*>',
                        '<meta name="author" content="頤典 DOUBTS 公版範例">', '作者')
    head = pattern_once(head, r'<meta\s+name="keywords"\s+content="[^"]*"\s*>',
                        '<meta name="keywords" content="頤典,DOUBTS,公版範例">', '關鍵字')
    # No API-capable frontend JavaScript from the source booking application.
    head = re.sub(r'<script\b[^>]*>[\s\S]*?</script\s*>', '', head, flags=re.I)
    head = once(head, '</head>', '<style id="demo-empty-home-style">' + STYLE + '</style></head>', '樣式')

    header = region(source, '<header id="header"', '</header>')
    header = once(header, 'href="index.html"', 'href="/?clinic=yidian"', '首頁連結')
    header = once(header, 'href="appointment.html"', 'href="#scrollspyAppointment"', '預約連結')
    header = once(header,
                  'href="#"\n    onclick="openSelfPayBrowser(); return false;"',
                  'href="#scrollspyAppointment"', '自費連結')
    header = once(header, 'href="https://a112070089.github.io/shanlin-bot/admin.html"',
                  'href="/pilot?clinic=yidian&amp;view=admin"', '後台連結')
    header = once(header, '<img src="./assets/img/branding/logo.png" class="bsb-tpl-logo" alt="">',
                  '', '品牌圖示')

    main = region(source, '<main id="main">', '</main>')
    main = once(main, '115年臺北市<br />老人健康檢查',
                '頤典診所<br />公版範例', '主視覺標題')
    marker = '<div class="d-grid gap-2 d-sm-flex flex-wrap mt-4 senior-hero-actions-v14">'
    if main.count(marker) != 1:
        raise HTTPException(503, '公版首頁服務按鈕結構變更，暫停展示')
    a = main.index(marker)
    b = main.index('</div>', a) + len('</div>')
    main = main[:a] + '''<div class="d-grid gap-2 d-sm-flex flex-wrap mt-4 senior-hero-actions-v14">
      <button type="button" disabled aria-disabled="true" class="btn btn-primary bsb-btn-2xl rounded-pill">一般預約（尚未設定）</button>
      <button type="button" disabled aria-disabled="true" class="btn btn-outline-primary bsb-btn-2xl rounded-pill d-flex align-items-center justify-content-center">老人健檢語音助理（尚未設定）</button>
      <button type="button" disabled aria-disabled="true" class="btn btn-outline-primary bsb-btn-2xl rounded-pill d-flex align-items-center justify-content-center">自費項目（尚未設定）</button>
    </div>''' + main[b:]
    main = once(main, '先了解三個步驟，再選擇健檢方案。',
                '這裡是沒有任何正式健檢內容的空白公版；導入診所後，才由該診所建立並核准服務資料。', '流程說明')
    steps = '<ol class="elderly-booking-steps" aria-label="健檢流程三步驟">'
    if main.count(steps) != 1:
        raise HTTPException(503, '公版首頁步驟區格式變更，暫停展示')
    a = main.index(steps)
    b = main.index('</ol>', a) + len('</ol>')
    items = (
        ('設定診所資料', '聯絡方式、醫師與營業時間尚未設定。'),
        ('建立檢查與套組', '尚未新增檢查項目、套組內容與價格。'),
        ('審核後開放服務', '診所資料、預約時段與後端隔離完成後再正式開放。'),
    )
    new_steps = [steps]
    for index, (title, desc) in enumerate(items, 1):
        new_steps.append(f'''<li class="elderly-booking-step">
            <span class="elderly-step-number" aria-hidden="true">{index}</span>
            <div class="elderly-step-content"><h3>{title}</h3><p>{desc}</p></div>
          </li>''')
    new_steps.append('</ol>')
    main = main[:a] + '\n'.join(new_steps) + main[b:]
    main = once(main, '※ 受檢資格須由診所現場確認。',
                '※ 空白公版僅展示介面，沒有正式項目、價格、醫療服務或預約資料。', '資格說明')
    main = once(main, '<h2 id="elderlyBookingTitle">預約健檢</h2>',
                '<h2 id="elderlyBookingTitle">公版設定流程</h2>', '流程標題')
    main = once(main, '<h2 id="elderlyPlansTitle">健檢方案</h2>',
                '<h2 id="elderlyPlansTitle">健檢方案（尚未建立）</h2>', '方案標題')
    main = once(main, '先看主要項目；如需詳細資訊，可展開完整清單。',
                '目前沒有任何健檢方案、檢查清單或價格；下方只展示方案卡片的空白版型。', '方案說明')
    grid = '<div class="elderly-plan-grid" aria-labelledby="elderlyPlansTitle">'
    grid_end = '\n      </div>\n    </section>'
    if main.count(grid) != 1 or grid_end not in main[main.index(grid):]:
        raise HTTPException(503, '公版首頁方案卡片格式變更，暫停展示')
    a = main.index(grid)
    b = main.index(grid_end, a)
    cards = [grid]
    for index in (1, 2, 3):
        cards.append(f'''<article class="elderly-plan-card" data-demo-empty="true" aria-labelledby="demoPlan{index}">
          <div class="elderly-plan-header"><span class="elderly-plan-code">範例欄位 {index}</span>
            <h3 id="demoPlan{index}">尚未建立方案</h3></div>
          <p class="elderly-plan-preview-label">檢查項目</p>
          <ul class="elderly-plan-preview demo-empty-preview"><li>尚未設定</li></ul>
          <p class="demo-empty-text">尚未新增檢查細項、套組或價格。</p>
          <span class="elderly-plan-action" aria-disabled="true">尚未開放預約</span>
        </article>''')
    cards.append('</div>')
    main = main[:a] + '\n'.join(cards) + main[b:]

    footer = region(source, '<footer class="footer">', '</footer>')
    footer = pattern_once(footer, r'<address class="mb-4" data-clinic="address">.*?</address>',
                          '<address class="mb-4">地址尚未設定（公版範例）</address>', '頁尾地址')
    footer = pattern_once(footer, r'<p class="mb-4"><a[^>]*data-clinic="phone"[^>]*>.*?</a></p>',
                          '<p class="mb-4">電話及營業時間尚未設定</p>', '頁尾電話')
    footer = pattern_once(footer, r'<div class="copyright[^>]*>.*?</div>',
                          '<div class="copyright text-center text-md-start">頤典 DOUBTS · 空白公版展示</div>', '頁尾資訊')

    notice = '''<div class="demo-notice" id="integrated-clinic-home-notice" role="status">
      頤典 DOUBTS · 空白公版範例：尚未建立健檢項目、價格、醫師或時段。
      這裡不接受病患資料，也不能送出預約。
    </div>'''
    output = (head + '\n<body>\n' + notice + '\n' + header + '\n' + main +
              '\n' + footer + '\n' +
              '<script defer src="https://unpkg.com/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>' +
              '\n</body>\n</html>')
    forbidden = ('<form', '<input', 'onclick=', 'onpointer', 'site-config.js',
                 'clinic.js', 'yidian_speech.js', 'booking_questions.js',
                 'appointment2.html', '/api/self_pay', '/api/booking',
                 '山林', 'shanlin', '115年臺北市', '臺北市文山區',
                 '羅斯福路', '02 2933 2010', '胸部X光',
                 '腦肺方案', '腹部方案', '骨密肌力方案', '血脂肪檢查',
                 '血液檢測', '甲狀腺刺激素', 'NT$', 'A 方案', 'B 方案', 'C 方案')
    if any(item in output for item in forbidden):
        raise HTTPException(503, '公版首頁含其他診所的內容或舊預約表單，已停止展示')
    return HTMLResponse(output, headers={**headers, 'Content-Security-Policy': CSP})
