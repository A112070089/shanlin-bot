"""Local-only Shanlin SYNTHETIC patient booking bridge.

Uses the verified staff HMAC-to-8018 transport, hence the SAME RTDB transaction.
Never calls the legacy /api/booking/confirm handler or a production database.
Only elderly A/B/C dummy bookings; real patients and self-pay remain disabled.
"""
from __future__ import annotations

from copy import copy
from datetime import date
import json
import os
import re
from urllib.parse import parse_qs, urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from integrated_app_platform_booking_unified import app as original
from integrated_clinic_routes import local_only, valid_clinic, preview_config
from integrated_home_restore import HEADERS, scoped_booking_preview
from platform_shanlin_booking_stage import _relay

app = copy(original)
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
        original_target = '`${API_BASE}/api/booking/confirm`'
        if html.count(original_target) != 1:
            raise HTTPException(503, '病患預約送出版本已變動，保留安全鎖定')
        html = html.replace(original_target,
            '`${API_BASE}/api/patient/shanlin/booking-test/confirm?clinic=shanlin`', 1)
        success = '"booking_success.html"'
        if html.count(success) != 1:
            raise HTTPException(503, '預約完成頁面診所識別碼未通過驗證')
        html = html.replace(success, '"booking_success.html?clinic=shanlin"', 1)
        # Display fake-data restrictions at the point where a patient enters a form.
        html = html.replace('請勿輸入真實病患個資。',
            '僅限合成測試：姓名 DOUBTS病患測試05、手機 0999999905、測試身分證 A123456789；不得輸入任何真實病患資料。自費預約尚未開放。', 1)
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


@router.post('/api/patient/shanlin/booking-test/confirm', include_in_schema=False)
async def synthetic_patient_booking(request: Request, clinic: str | None = None):
    local_only(request)
    if clinic != 'shanlin':
        raise HTTPException(423, '不是山林診所測試入口')
    if os.getenv('PILOT_V365_SYNTHETIC_BOOKINGS_ENABLED') != '1':
        raise HTTPException(423, '本機合成測試預約尚未啟用')
    if request.headers.get('origin', '').rstrip('/') != str(request.base_url).rstrip('/'):
        raise HTTPException(403, '拒絕非同源預約請求')
    ref = urlsplit(request.headers.get('referer', ''))
    if (f'{ref.scheme}://{ref.netloc}' != str(request.base_url).rstrip('/')
            or ref.path != '/appointment2.html' or parse_qs(ref.query).get('clinic') != ['shanlin']):
        raise HTTPException(403, '請由山林測試預約頁送出')
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
    if data.get('birthday') not in ('', None, '1950-01-01'):
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
