"""Local-only Shanlin SYNTHETIC patient booking bridge.

Uses the verified staff HMAC-to-8018 transport, hence the SAME RTDB transaction.
Never calls the legacy /api/booking/confirm handler or a production database.
Only elderly A/B/C dummy bookings; real patients and self-pay remain disabled.
"""
from __future__ import annotations

from copy import copy
from datetime import date
from pathlib import Path
import hmac
import json
import os
import re
import secrets
from urllib.parse import parse_qs, urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from integrated_app_platform_booking_unified import app as original
from integrated_clinic_routes import local_only, valid_clinic, preview_config
from integrated_home_restore import HEADERS, scoped_booking_preview
from platform_shanlin_booking_stage import _relay

app = copy(original)

# SHANLIN_NONPERSISTENT_DEMO_20261120_V1
from shanlin_no_write_demo import router as _shanlin_no_write_demo_router
app.include_router(_shanlin_no_write_demo_router)
app.router = type(original.router)(
    routes=list(original.router.routes),
    redirect_slashes=original.router.redirect_slashes,
    on_startup=list(original.router.on_startup),
    on_shutdown=list(original.router.on_shutdown),
    lifespan=original.router.lifespan_context,
    dependency_overrides_provider=original.router.dependency_overrides_provider,
    route_class=original.router.route_class,
)
app.user_middleware = list(original.user_middleware)
app.middleware_stack = None
app.openapi_schema = None
router = APIRouter()
TEST_PHONE = re.compile(r'09999999\d{2}\Z')
TEST_NAME = re.compile(r'DOUBTS(?:病患|網站|語音|測試)[^\d\s]{0,6}\d{2}\Z')
ELDERLY = {'A', 'B', 'C'}
DAY = re.compile(r'\d{4}-\d{2}-\d{2}\Z')
TIME = re.compile(r'(?:[01]\d|2[0-3]):[0-5]\d\Z')
# Local-only, process-bound anti-CSRF token. Never use the 8018 service secret in HTML.
PAGE_TOKEN = secrets.token_urlsafe(32)


def _data():
    """HMAC-bound localhost source, no new credentials or booking storage."""
    if os.getenv('PILOT_V365_SYNTHETIC_BOOKINGS_ENABLED') != '1':
        raise HTTPException(423, '本機合成測試預約尚未啟用')
    value = _relay('GET')
    schedule = value.get('testSchedule')
    if not isinstance(schedule, dict):
        raise HTTPException(503, '8018 尚未提供測試名額設定，請先更新並重新啟動 8018')
    days, hours, caps = (schedule.get('elderlyDates'),
                         schedule.get('elderlyTimes'), schedule.get('capacityBySlot'))
    if (not isinstance(days, list) or not isinstance(hours, list)
            or not isinstance(caps, dict) or not 0 < len(days) <= 100
            or not 0 < len(hours) <= 30 or any(not isinstance(d, str) or not DAY.fullmatch(d) for d in days)
            or any(not isinstance(h, str) or not TIME.fullmatch(h) for h in hours)):
        raise HTTPException(503, '測試診所時段資料不正確')
    for day, slots in caps.items():
        if day not in days or not isinstance(slots, dict):
            raise HTTPException(503, '測試名額日期不符')
        for slot, limit in slots.items():
            if slot not in hours or type(limit) is not int or not (1 <= limit <= 100):
                raise HTTPException(503, '測試名額格式不正確')
    rows = value.get('appointments')
    if not isinstance(rows, list):
        raise HTTPException(503, '測試預約回傳格式不正確')
    return days, hours, caps, rows


def _counts(days, hours, caps, rows):
    occupied = {day: {hour: 0 for hour in hours if hour in (caps.get(day) or {})} for day in days}
    selfpay = {}
    for row in rows:
        if not isinstance(row, dict):
            raise HTTPException(503, '測試預約格式不正確')
        if row.get('cancelled') is True or str(row.get('status') or '').strip().lower() in ('cancelled', 'canceled', '已取消'):
            continue
        if row.get('plan') == 'SELF_PAY':
            day = row.get('selfPayDate') or row.get('date')
            if day in days:
                selfpay[day] = selfpay.get(day, 0) + 1
            continue
        day, hour = row.get('date'), row.get('time')
        if day in occupied and hour in occupied[day]:
            occupied[day][hour] += 1
    daily = {day: sum(slot_counts.values()) for day, slot_counts in occupied.items()}
    availability = {
        day: {slot: {'capacity': caps[day][slot], 'occupied': count,
                     'remaining': max(0, caps[day][slot] - count),
                     'full': count >= caps[day][slot]}
              for slot, count in slot_counts.items()}
        for day, slot_counts in occupied.items()
    }
    return daily, selfpay, availability


@router.get('/api/clinic-config', include_in_schema=False)
def clinic_config(request: Request, clinic: str | None = None):
    local_only(request)
    if clinic not in ('shanlin', 'yidian'):
        raise HTTPException(423, '須由指定診所首頁進入')
    if clinic == 'yidian':
        return JSONResponse({'status':'success', 'clinicId':'yidian', 'previewOnly':True,
                             'clinic':preview_config()}, headers=HEADERS)
    days, hours, caps, _ = _data()
    # No old global Firebase clinic config, and no fabricated public contact info.
    config = {**preview_config(), 'name':'山林診所',
              'elderlyDates':days, 'elderlyTimes':hours,
              'capacityBySlot':caps}
    # The old booking selector also checks a weekday timetable. Derive its
    # test-only flags from the SAME opened slots (not the Yidian timetable).
    weekdays = ('mon','tue','wed','thu','fri','sat','sun')
    for day in days:
        weekday = weekdays[date.fromisoformat(day).weekday()]
        for slot in caps.get(day, {}):
            label = 'morning' if slot < '12:00' else 'afternoon' if slot < '18:00' else 'evening'
            if label not in config['selfPayWeekly'][weekday]:
                config['selfPayWeekly'][weekday].append(label)
    return JSONResponse({'status':'success','clinicId':'shanlin','previewOnly':True,
                         'isSynthetic':True,'clinic':config}, headers=HEADERS)


@router.get('/api/availability', include_in_schema=False)
def availability(request: Request, clinic: str | None = None):
    local_only(request)
    if clinic not in ('shanlin', 'yidian'):
        raise HTTPException(423, '須由指定診所首頁進入')
    if clinic == 'yidian':
        return JSONResponse({'status':'success','clinicId':'yidian','previewOnly':True,
                             'elderly':{}, 'selfPay':{}, 'slots':{}}, headers=HEADERS)
    days, hours, caps, rows = _data()
    elderly, selfpay, slots = _counts(days, hours, caps, rows)
    return JSONResponse({'status':'success','clinicId':'shanlin', 'isSynthetic':True,
                         'elderly':elderly, 'selfPay':selfpay, 'slots':slots}, headers=HEADERS)


def _shanlin_booking_schedule_page(html: str) -> str:
    """Scope legacy clinic.js reads to the test 8006 source; no old dates on failure.

    Legacy site-config.js points bookingApi at :8000. The legacy JS must still
    use that port for unrelated speech APIs, but clinic dates/availability are
    served only by this localhost 8006 -> signed 8018 test bridge.
    """
    anchor = '<script src="clinic.js" data-api="booking"></script>'
    if html.count(anchor) != 1:
        raise HTTPException(503, '山林日期設定載入版本已變動，暫停測試')
    # Execute BEFORE clinic.js initializes/fetches. Leave unrelated API calls
    # untouched; never ship another bookingApi address into the original file.
    bridge = r"""<script id="shanlin-test-clinic-read-bridge">
(function () {
  'use strict';
  const nativeFetch = window.fetch.bind(window);
  window.fetch = function (input, init) {
    try {
      const src = input instanceof Request ? input.url : String(input);
      const url = new URL(src, window.location.href);
      const method = (init && init.method ? String(init.method) :
        (input instanceof Request ? input.method : 'GET')).toUpperCase();
      const isGet = method === 'GET';
      // The page intentionally sets Referrer-Policy: no-referrer to prevent
      // birth date / ID in legacy form URLs from leaking. Explicitly prove this
      // same-origin synthetic POST came from the rendered test page instead.
      if (method === 'POST' && url.origin === location.origin &&
          url.pathname === '/api/patient/shanlin/booking-test/confirm' &&
          url.searchParams.get('clinic') === 'shanlin') {
        // Refresh the process-bound token immediately before this submission.
        // No form data is sent to this context endpoint; cross-origin access is rejected.
        return nativeFetch('/api/patient/shanlin/booking-test/page-context?clinic=shanlin', {
          method: 'GET', mode: 'same-origin', credentials: 'same-origin',
          cache: 'no-store', redirect: 'error', referrerPolicy: 'no-referrer',
          headers: {'X-DOUBTS-Page-Context': 'shanlin-booking'}
        }).then(async function (response) {
          if (!response.ok) throw new Error('無法更新預約頁驗證，請重新開啟預約頁面');
          const context = await response.json();
          if (context.clinicId !== 'shanlin' || typeof context.pageToken !== 'string' ||
              !/^[A-Za-z0-9_-]{40,100}$/.test(context.pageToken)) {
            throw new Error('預約頁驗證回應不正確，尚未送出資料');
          }
          const outgoingHeaders = new Headers((init && init.headers) ||
            (input instanceof Request ? input.headers : undefined));
          outgoingHeaders.set('X-DOUBTS-Patient-Test-Page', context.pageToken);
          return nativeFetch(input, { ...(init || {}), headers: outgoingHeaders });
        });
      }
      // Unrelated config lookup must not prevent the booking token from being sent.
      const configured = new URL((window.SITE || {}).bookingApi || location.origin, location.origin);
      if (isGet && (url.origin === configured.origin || url.origin === location.origin) &&
          (url.pathname === '/api/clinic-config' || url.pathname === '/api/availability')) {
        const local = new URL(url.pathname, location.origin);
        local.searchParams.set('clinic', 'shanlin');
        const outgoing = input instanceof Request ? new Request(local.toString(), input) : local.toString();
        return nativeFetch(outgoing, init);
      }
    } catch (_) { /* Invalid URL: allow browser to reject it normally. */ }
    return nativeFetch(input, init);
  };
  try { sessionStorage.removeItem('clinicConfig'); } catch (_) { /* Browsers may disable storage. */ }
})();
</script>
"""
    # Page context is fetched at submit time; no process token is embedded in HTML.
    html = html.replace(anchor, bridge + anchor, 1)
    # Source HTML contains old 11/02, 11/04, 11/09 options and 08:00.
    # With a down test API those must NOT appear as selectable appointments.
    for key in ('elderlyDates', 'elderlyTimes'):
        pattern = (r'(<select\b[^>]*\bdata-clinic-options="' + key +
                   r'"[^>]*>)(.*?)(</select>)')
        def placeholder(match):
            if '<option' not in match.group(2):
                raise HTTPException(503, '山林預約日期欄位版本已變動')
            return (match.group(1) +
                    '<option value="">--請等候測試名額載入--</option>' + match.group(3))
        html, changed = re.subn(pattern, placeholder, html, count=1, flags=re.I | re.S)
        if changed != 1:
            raise HTTPException(503, '山林預約日期欄位版本已變動')
    return html


def _patient_page(filename, clinic):
    valid_clinic(clinic)
    if clinic != 'shanlin':
        return RedirectResponse('/?clinic=yidian#scrollspyAppointment', status_code=303, headers=HEADERS)
    source = scoped_booking_preview(filename, 'shanlin')
    html = source.body.decode('utf-8')
    if filename == 'appointment.html':
        anchor = '"appointment2.html?p=" + p +'
        if html.count(anchor) != 1:
            raise HTTPException(503, '病患預約跨頁識別碼未通過驗證')
        html = html.replace(anchor, '"appointment2.html?clinic=shanlin&p=" + p +', 1)
    if filename == 'appointment2.html':
        html = _shanlin_booking_schedule_page(html)
        original_target = '`${API_BASE}/api/booking/confirm`'
        if html.count(original_target) != 1:
            raise HTTPException(503, '病患預約送出版本已變動，保留安全鎖定')
        # The legacy API_BASE is :8000; submit MUST go to the 8006 HMAC bridge.
        html = html.replace(original_target,
            '`/api/patient/shanlin/booking-test/confirm?clinic=shanlin`', 1)
        success = '"booking_success.html"'
        if html.count(success) != 1:
            raise HTTPException(503, '預約完成頁面診所識別碼未通過驗證')
        html = html.replace(success, '"booking_success.html?clinic=shanlin"', 1)
        # Shanlin-only, inline field hints. Do not alter the original template,
        # existing captcha, or the backend's final synthetic-data checks.
        script_path = Path(__file__).with_name('shanlin_patient_field_validation.js')
        if not script_path.is_file():
            raise HTTPException(503, '本機山林欄位驗證檔案遺失，暫停測試預約')
        form_validation_js = script_path.read_text(encoding='utf-8')
        if '</script' in form_validation_js.lower() or html.count('</body>') != 1:
            raise HTTPException(503, '山林預約表單驗證版本不符，暫停測試預約')
        html = html.replace('</body>',
            '<script id="shanlin-patient-field-validation">\n' +
            form_validation_js + '\n</script>\n</body>', 1)
        # Display fake-data restrictions at the point where a patient enters a form.
        html = html.replace('請勿輸入真實病患個資。',
            '本機展示模式：請使用虛構資料。送出時會轉換為固定合成測試身分，不傳送輸入的個人識別資料至共用預約服務。自費預約尚未開放。', 1)
    return HTMLResponse(html, headers={**HEADERS,'X-Clinic-Id':'shanlin',
                                      'Content-Security-Policy':"frame-ancestors 'none'"})


@router.get('/appointment.html', include_in_schema=False)
def appointment_one(request: Request, clinic: str | None = None):
    local_only(request)
    return _patient_page('appointment.html', clinic)


@router.get('/appointment2.html', include_in_schema=False)
def appointment_two(request: Request, clinic: str | None = None):
    local_only(request)
    return _patient_page('appointment2.html', clinic)


@router.get('/api/patient/shanlin/booking-test/page-context', include_in_schema=False)
def patient_booking_page_context(request: Request, clinic: str | None = None):
    local_only(request)
    if clinic != 'shanlin':
        raise HTTPException(423, '不是山林診所測試入口')
    if os.getenv('PILOT_V365_SYNTHETIC_BOOKINGS_ENABLED') != '1':
        raise HTTPException(423, '本機合成測試預約尚未啟用')
    origin = str(request.base_url).rstrip('/')
    supplied_origin = request.headers.get('origin', '').rstrip('/')
    if supplied_origin and supplied_origin != origin:
        raise HTTPException(403, '拒絕跨站取得預約頁驗證')
    if request.headers.get('sec-fetch-site', '') not in ('', 'same-origin'):
        raise HTTPException(403, '拒絕跨站取得預約頁驗證')
    if request.headers.get('x-doubts-page-context') != 'shanlin-booking':
        raise HTTPException(403, '缺少預約頁驗證請求標頭')
    return JSONResponse({'clinicId':'shanlin','pageToken':PAGE_TOKEN},
                        headers={**HEADERS,'Cache-Control':'no-store','Pragma':'no-cache',
                                 'Vary':'Origin, Sec-Fetch-Site'})


@router.post('/api/patient/shanlin/booking-test/confirm', include_in_schema=False)
async def synthetic_patient_booking(request: Request, clinic: str | None = None):
    local_only(request)
    if clinic != 'shanlin':
        raise HTTPException(423, '不是山林診所測試入口')
    if os.getenv('PILOT_V365_SYNTHETIC_BOOKINGS_ENABLED') != '1':
        raise HTTPException(423, '本機合成測試預約尚未啟用')
    if request.headers.get('origin', '').rstrip('/') != str(request.base_url).rstrip('/'):
        raise HTTPException(403, '拒絕非同源預約請求')
    # Preserve the legacy Referer gate for backwards-compatible tests, but
    # accept an explicit page token when the privacy header rightly omits it.
    # Exact Origin validation above remains mandatory for BOTH paths.
    ref = urlsplit(request.headers.get('referer', ''))
    referer_ok = (f'{ref.scheme}://{ref.netloc}' == str(request.base_url).rstrip('/')
                  and ref.path == '/appointment2.html'
                  and parse_qs(ref.query).get('clinic') == ['shanlin'])
    supplied_token = request.headers.get('x-doubts-patient-test-page', '')
    token_ok = bool(supplied_token) and hmac.compare_digest(supplied_token, PAGE_TOKEN)
    if not (referer_ok or token_ok):
        raise HTTPException(403, '山林測試預約頁驗證失敗，請重新整理頁面')
    if not request.headers.get('content-type','').lower().startswith('application/json'):
        raise HTTPException(415, '僅接受 JSON')
    body = await request.body()
    if len(body) > 8192:
        raise HTTPException(413, '測試資料過長')
    try:
        data = json.loads(body)
    except (ValueError, UnicodeError):
        raise HTTPException(422, '預約資料格式錯誤') from None
    if not isinstance(data, dict):
        raise HTTPException(422, '預約資料格式錯誤')
    # Reject unsupported flows before consulting the synthetic appointment database.
    # This is an explicit limitation, not a booking success or a failed page token.
    if data.get('plan') not in ELDERLY:
        raise HTTPException(423, '此測試入口目前僅支援老人健檢；自費預約尚未開放送出')
    if (data.get('selfPayItems') or data.get('selfPayDate') or data.get('selfPayTime')
            or data.get('extraAnswers')):
        raise HTTPException(423, '此測試入口尚未開放自費加購或問診資料送出')
    # SHANLIN_DEMO_INPUT_NORMALIZATION_V1
    # Local synthetic demonstration only.
    import re as _demo_re
    from datetime import date as _demo_date

    demo_name = data.get('name')
    demo_phone = data.get('phone')
    demo_pid = data.get('pid')
    demo_dob = data.get('birthday')

    if (not isinstance(demo_name, str)
            or not 1 <= len(demo_name.strip()) <= 50
            or not demo_name.isprintable()
            or not any(c.isalpha() for c in demo_name)):
        raise HTTPException(422, '姓名格式不正確')

    if (not isinstance(demo_phone, str)
            or not _demo_re.fullmatch(r'09[0-9]{8}', demo_phone)):
        raise HTTPException(422, '手機須為09開頭的10碼數字')

    if not isinstance(demo_pid, str):
        raise HTTPException(422, '身分證字號格式不正確')

    demo_pid = demo_pid.strip().upper()

    if not _demo_re.fullmatch(r'[A-Z][12][0-9]{8}', demo_pid):
        raise HTTPException(422, '身分證字號格式不正確')

    letters = 'ABCDEFGHJKLMNPQRSTUVXYWZIO'
    idx = letters.find(demo_pid[0])
    digits = str(idx + 10) + demo_pid[1:]
    weights = (1, 9, 8, 7, 6, 5, 4, 3, 2, 1, 1)

    if idx < 0 or sum(
            int(d) * w for d, w in zip(digits, weights)
        ) % 10:
        raise HTTPException(422, '身分證檢查碼不正確')

    try:
        if not isinstance(demo_dob, str):
            raise ValueError()

        if _demo_re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', demo_dob):
            y, m, d = map(int, demo_dob.split('-'))
        elif _demo_re.fullmatch(r'[0-9]{6,7}', demo_dob):
            roc_year = int(demo_dob[:-4])
            if roc_year < 1:
                raise ValueError()
            y = 1911 + roc_year
            m = int(demo_dob[-4:-2])
            d = int(demo_dob[-2:])
        else:
            raise ValueError()

        born = _demo_date(y, m, d)
    except (ValueError, TypeError):
        raise HTTPException(422, '出生日期不正確')

    today = _demo_date.today()
    age = today.year - born.year - (
        (today.month, today.day) < (born.month, born.day)
    )

    if y < 1850 or age < 65:
        raise HTTPException(422, '高齡健檢須年滿65歲')

    # Never forward entered identity to the synthetic booking database.
    # SHANLIN_UNIQUE_SYNTHETIC_IDENTITY_V2
    # Read the isolated synthetic appointment list before assigning an identity.
    # Never forward visitor-entered name, phone or national ID.

    snapshot = _relay('GET')

    if snapshot.get('clinicId') != 'shanlin' or snapshot.get('isSynthetic') is not True:
        raise HTTPException(503, '合成測試資料來源驗證失敗')

    used_phones = set()

    for field in ('appointments', 'self_pay_booking', 'selfPayBookings'):
        rows = snapshot.get(field)
        if rows is None:
            if field == 'appointments':
                raise HTTPException(503, '合成預約清單格式不正確')
            continue
        if isinstance(rows, dict):
            entries = list(rows.values())
        elif isinstance(rows, list):
            entries = rows
        else:
            raise HTTPException(503, '合成預約資料結構不正確')

        if not all(isinstance(row, dict) for row in entries):
            raise HTTPException(503, '合成預約資料格式不正確')

        for row in entries:
            number = str(row.get('phone') or '').replace('-', '').replace(' ', '')
            if number:
                used_phones.add(number)

    candidates = []

    for number in range(100):
        fake_name = f'DOUBTS病患測試{number:02d}'
        fake_phone = f'09999999{number:02d}'

        if (TEST_NAME.fullmatch(fake_name)
                and TEST_PHONE.fullmatch(fake_phone)
                and fake_phone not in used_phones):
            candidates.append((fake_name, fake_phone))

    if not candidates:
        raise HTTPException(
            503,
            '可用的虛構測試身分已用盡，請由管理員檢查測試資料'
        )

    fake_name, fake_phone = secrets.choice(candidates)

    data['name'] = fake_name
    data['phone'] = fake_phone
    data['pid'] = 'A123456789'
    data['birthday'] = '450101'

    name, phone, plan = data.get('name'), data.get('phone'), data.get('plan')
    if (not isinstance(name, str) or not TEST_NAME.fullmatch(name)
            or not isinstance(phone,str) or not TEST_PHONE.fullmatch(phone)
            or data.get('pid') != 'A123456789'):
        raise HTTPException(422, '只能使用畫面指定的虛構測試姓名、手機與身分證')
    if plan not in ELDERLY:
        raise HTTPException(423, '自費健檢尚未接入共用交易層，禁止提交')
    if (data.get('selfPayItems') or data.get('selfPayDate') or data.get('selfPayTime')
            or data.get('extraAnswers')):
        raise HTTPException(423, '自費加購或問診資料尚未完成測試隔離，禁止提交')
    # The original form asks for ROC-format DOB (450101); fake DOB is never relayed.
    if data.get('birthday') not in ('', None, '1950-01-01', '390101', '450101'):
        raise HTTPException(422, '僅限虛構生日，不得填寫真實病患資料')
    veg = data.get('breakfast') or ''
    veg = {'1':'葷','2':'素','葷':'葷','素':'素','葷食':'葷','素食':'素'}.get(veg)
    if veg is None:
        raise HTTPException(422, '葷素選項不正確')
    entry = {'name':name,'phone':phone,'plan':plan,
             'date':data.get('date'), 'time':data.get('time'),
             'source':'網站合成測試','veg':veg}
    # _relay checks configured shared secret, 8018's HMAC, synthetic DB identity,
    # time-slot capacity, duplicates and atomic RTDB transaction before success.
    answer = _relay('POST',payload=entry)
    if answer.get('status') != 'success' or answer.get('action') != 'create':
        raise HTTPException(503,'測試預約結果無法確認')
    return JSONResponse({'status':'success','message':'山林合成測試預約已建立',
                         'clinicId':'shanlin','isSynthetic':True,
                         'booking':{'testKey':answer.get('key')},
                         'selfPayCount':0,'selfPayTotal':0}, headers=HEADERS)


start = len(app.router.routes)
app.include_router(router)
extra = app.router.routes[start:]
del app.router.routes[start:]
app.router.routes[0:0] = extra

# DOUBTS-OCR-8006-STATIC-ROUTE-V1 BEGIN
# Allow local OCR assets to be read by the 8006 integrated website. This mount
# is active ONLY in the existing synthetic-booking testing environment.
# StaticFiles prevents traversal beyond the dedicated idscan directory.
def _doubts_enable_idscan_static_v1():
    import os as _doubts_os
    from pathlib import Path as _doubts_path
    if _doubts_os.environ.get("PILOT_V365_SYNTHETIC_BOOKINGS_ENABLED") != "1":
        return
    from starlette.staticfiles import StaticFiles as _doubts_static
    from starlette.routing import Mount as _doubts_mount
    _doubts_dir = _doubts_path(__file__).resolve().parent / "idscan"
    if not (_doubts_dir / "idscan.js").is_file() or not (_doubts_dir / "idscan_core.js").is_file():
        return
    if not any(getattr(_r, "name", None) == "doubts_idscan_static_v1" for _r in app.router.routes):
        # Put this narrowly scoped path before an optional SPA catch-all.
        app.router.routes.insert(0, _doubts_mount(
            "/idscan", app=_doubts_static(directory=str(_doubts_dir)),
            name="doubts_idscan_static_v1"
        ))
_doubts_enable_idscan_static_v1()
del _doubts_enable_idscan_static_v1
# DOUBTS-OCR-8006-STATIC-ROUTE-V1 END
