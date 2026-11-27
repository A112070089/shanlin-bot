"""Local 8006 -> existing online Shanlin booking API, with no Firebase credentials.

This ASGI adapter preserves local speech routes and the original application.
It never calls the isolated 8018 writer. No automatic POST retries or redirects.
"""
from __future__ import annotations

import hmac
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, Response
import integrated_app_platform_patient_stage as legacy

ONLINE = 'https://shanlin-website-production.up.railway.app'
LOCAL = frozenset({'127.0.0.1', 'localhost', '::1', 'testclient'})
HEADERS = {'Cache-Control':'no-store, private', 'Pragma':'no-cache',
           'Referrer-Policy':'no-referrer', 'X-Content-Type-Options':'nosniff'}
MAX_REQUEST = 65536
MAX_RESPONSE = 2 * 1024 * 1024
CONFIRM = '/api/patient/shanlin/booking-test/confirm'
PAGES = {'/', '/index.html', '/appointment.html', '/appointment2.html', '/booking_success.html'}


def readable(path):
    return path in ('/api/clinic-config', '/api/availability', '/api/questions') or bool(
        re.fullmatch(r'/api/self_pay(?:/[A-Za-z0-9_-]+)*', path))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def upstream(method, path, query='', body=None):
    """One request to a fixed origin. Never relay browser cookies or credentials."""
    url = ONLINE + path + ('?' + query if query else '')
    req = Request(url, data=body, method=method,
                  headers={'Accept':'application/json', 'Content-Type':'application/json'})
    try:
        try:
            response = build_opener(ProxyHandler({}), NoRedirect()).open(req, timeout=20)
        except HTTPError as exc:
            response = exc
        with response:
            status = response.code
            raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE or 300 <= status < 400:
            raise ValueError('unexpected upstream response')
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError('unexpected upstream shape')
        return status, value
    except (OSError, URLError, ValueError, TimeoutError):
        # A timed-out POST may already be stored upstream; never suggest a blind retry.
        message = ('預約結果尚未確認，請先到後台查詢，避免重複送出。' if method == 'POST'
                   else '無法讀取共用預約服務，請稍後重新整理。')
        return 503, {'detail': message}


BOOTSTRAP = r'''<script id="shanlin-shared-booking-source-v1">
(function(){
'use strict';
window.DoubtsSharedBooking={mode:'shared-online',clinicId:'shanlin'};
const nativeFetch=window.fetch.bind(window);
window.fetch=function(input,init){
 try{
  const url=new URL(input instanceof Request?input.url:String(input),location.href);
  const method=String(init?.method||(input instanceof Request?input.method:'GET')).toUpperCase();
  const configured=new URL(window.SITE?.bookingApi||location.origin,location.href);
  const allowed=url.origin===location.origin||url.origin===configured.origin;
  const read=/^\/api\/(clinic-config|availability|questions)$/.test(url.pathname)||/^\/api\/self_pay(?:\/[A-Za-z0-9_-]+)*$/.test(url.pathname);
  if(method==='GET'&&allowed&&read){
   const local=new URL(url.pathname,location.origin);local.search=url.search;local.searchParams.set('clinic','shanlin');
   return nativeFetch(input instanceof Request?new Request(local.toString(),input):local.toString(),init);
  }
 }catch(_){}
 return nativeFetch(input,init);
};
try{sessionStorage.removeItem('clinicConfig');}catch(_){}
})();
</script>'''
BIRTHDAY = '/* ONLINE_ROC_BIRTHDAY_PICKER_V1 — presentation only, no network requests. */\n(function () {\n  \'use strict\';\n  const params=new URLSearchParams(location.search);\n  if(!window.DoubtsSharedBooking||window.DoubtsSharedBooking.clinicId!==\'shanlin\')return;\n  if(params.has(\'clinic\')&&params.get(\'clinic\')!==\'shanlin\')return;\n  if(params.get(\'p\')===\'SELF_PAY\')return;\n  function dobError(raw) {\n    const value = String(raw || \'\').trim();\n    const western = /^(\\d{4})-(\\d{2})-(\\d{2})$/.exec(value);\n    const roc = /^(\\d{2,3})(\\d{2})(\\d{2})$/.exec(value);\n    if (!western && !roc) return \'請選擇正確的民國出生年月日。\';\n    if (roc && (Number(roc[1]) < 1 || Number(roc[1]) > 200))\n      return \'出生年份不正確，請重新確認。\';\n    const year = western ? Number(western[1]) : 1911 + Number(roc[1]);\n    const month = Number((western || roc)[2]);\n    const day = Number((western || roc)[3]);\n    if (year < 1850) return \'出生年份不正確，請重新確認。\';\n    const checked = new Date(year, month - 1, day);\n    if (month < 1 || month > 12 || day < 1 ||\n        checked.getFullYear() !== year || checked.getMonth() !== month - 1 || checked.getDate() !== day)\n      return \'出生年月日不存在，請重新確認。\';\n    const today = new Date();\n    let age = today.getFullYear() - year;\n    if (today.getMonth() + 1 < month ||\n        (today.getMonth() + 1 === month && today.getDate() < day)) age--;\n    return age < 65 ? \'高齡健檢須年滿65歲，請確認出生年月日。\' : \'\';\n  }\n\n\n  function init(){\n    const form=document.getElementById(\'bookingForm\');\n    if(!form||document.getElementById(\'shanlin-dob-picker\'))return;\n    const original=form.querySelector(\'input[name="birthday"]\');\n    if(!original)return;\n    const input={birthday:original};\n    const style=document.createElement(\'style\');\n    style.id=\'online-roc-birthday-style\';\n    style.textContent=[\n\'.shanlin-dob-picker{display:grid;grid-template-columns:1.55fr .8fr .8fr;gap:12px;padding:16px;background:#f1f7fa;border:2px solid #b5cbd8;border-radius:16px;margin-top:5px}\',\n\'.shanlin-dob-col{min-width:0}\',\n\'.shanlin-dob-col label{display:block;font-weight:700;font-size:1.1rem;margin-bottom:7px;color:#1c4156}\',\n\'#bookingForm select.shanlin-dob-wheel{width:100%;height:193px;box-sizing:border-box;overflow-y:auto;border:2px solid #9fbbcd;border-radius:10px;font-size:1.1rem;line-height:1.7;background:#fff;color:#203e52;padding:5px}\',\n\'#bookingForm select.shanlin-dob-wheel option{padding:6px 2px}\',\n\'#bookingForm select.shanlin-dob-wheel[size="1"]{height:56px}\',\n\'.shanlin-dob-picker.shanlin-picker-error select.shanlin-dob-wheel{border-color:#bd303d!important}\',\n\'.shanlin-dob-detail{grid-column:1/-1;font-size:1.05rem;font-weight:700;line-height:1.4;color:#24566e}\',\n\'@media(max-width:600px){.shanlin-dob-picker{gap:7px;padding:10px;grid-template-columns:1.55fr .78fr .78fr}.shanlin-dob-col label{font-size:1rem}#bookingForm select.shanlin-dob-wheel{font-size:1rem}}\'\n    ].join(\'\');\n    document.head.appendChild(style);\n    const error=document.createElement(\'div\');\n    error.id=\'shanlin-error-birthday\';\n    error.setAttribute(\'aria-live\',\'polite\');\n    error.style.cssText=\'color:#a4262c;font-size:1.05rem;font-weight:700;line-height:1.5;margin-top:7px\';\n    original.insertAdjacentElement(\'afterend\',error);\n    function validateBirthday(selects){\n      const complete=selects.year.value&&selects.month.value&&selects.day.value;\n      const message=complete?dobError(original.value):\'\';\n      selects.year.setCustomValidity(message);\n      error.textContent=message;\n      for(const select of Object.values(selects)){\n        if(message)select.setAttribute(\'aria-invalid\',\'true\');\n        else select.removeAttribute(\'aria-invalid\');\n      }\n    }\n    function rocYearLabel(year) {\n      return year >= 1912 ? \'民國 \' + (year - 1911) : \'民前 \' + (1912 - year);\n    }\n    function createBirthdayPicker() {\n      const original = input.birthday;\n      const parent = original.closest(\'.mb-3\') || original.parentElement;\n      const label = parent.querySelector(\'label\');\n      if (label) label.textContent = \'出生年月日（民國）＊年滿65歲\';\n      const hint = parent.querySelector(\'.hint-text\');\n      if (hint) hint.textContent = \'請選擇民國年、月、日，系統會依完整出生日期確認是否年滿65歲。\';\n      const previous = original.value || params.get(\'birthday\') || \'\';\n      original.type = \'hidden\'; // Keep the original name/FormData and AI flow.\n      original.removeAttribute(\'placeholder\');\n      const holder = document.createElement(\'div\');\n      holder.id = \'shanlin-dob-picker\';\n      holder.className = \'shanlin-dob-picker\';\n      holder.setAttribute(\'role\', \'group\');\n      holder.setAttribute(\'aria-label\', \'出生年月日三欄下拉選擇\');\n      const selects = {};\n      const wheelSize = 1;\n      for (const [key, text] of [[\'year\',\'民國年\'], [\'month\',\'月\'], [\'day\',\'日\']]) {\n        const col = document.createElement(\'div\');\n        col.className = \'shanlin-dob-col\';\n        const fieldLabel = document.createElement(\'label\');\n        fieldLabel.htmlFor = \'shanlin-dob-\' + key;\n        fieldLabel.textContent = text;\n        const select = document.createElement(\'select\');\n        select.id = fieldLabel.htmlFor;\n        select.className = \'shanlin-dob-wheel\';\n        select.size = wheelSize;\n        select.required = true;\n        select.setAttribute(\'aria-describedby\', \'shanlin-error-birthday\');\n        col.append(fieldLabel, select);\n        holder.appendChild(col);\n        selects[key] = select;\n      }\n      const detail = document.createElement(\'div\');\n      detail.className = \'shanlin-dob-detail\';\n      detail.id = \'shanlin-dob-detail\';\n      detail.setAttribute(\'role\', \'status\');\n      detail.textContent = \'請依序選擇民國年、月、日\';\n      holder.appendChild(detail);\n      original.insertAdjacentElement(\'afterend\', holder);\n\n      function fill(select, options, placeholder, restore) {\n        select.replaceChildren();\n        select.add(new Option(placeholder, \'\'));\n        for (const [value, label] of options) select.add(new Option(label, String(value)));\n        select.value = restore && Array.from(select.options).some(opt => opt.value === String(restore))\n          ? String(restore) : \'\';\n      }\n      const today = new Date();\n      const latestYear = today.getFullYear() - 65;\n      const years = [];\n      // Preserve the existing year range; pre-1912 years use 民前 labels.\n      for (let year = latestYear; year >= 1850; year--)\n        years.push([year, rocYearLabel(year)]);\n      fill(selects.year, years, \'選擇民國年\', \'\');\n      fill(selects.month, Array.from({length:12}, (_, i) => [i + 1, `${i + 1}月`]), \'選擇月\', \'\');\n      fill(selects.day, Array.from({length:31}, (_, i) => [i + 1, `${i + 1}日`]), \'選擇日\', \'\');\n\n      function months() {\n        const previous = selects.month.value;\n        fill(selects.month, Array.from({length:12}, (_, i) => [i + 1, `${i + 1}月`]), \'選擇月\', previous);\n      }\n      function days() {\n        const y = Number(selects.year.value), m = Number(selects.month.value);\n        const previous = selects.day.value;\n        const end = m ? new Date(y || 2024, m, 0).getDate() : 31;\n        fill(selects.day, Array.from({length:end}, (_, i) => [i + 1, `${i + 1}日`]), \'選擇日\', previous);\n      }\n      function update() {\n        const year = Number(selects.year.value), month = Number(selects.month.value);\n        const day = Number(selects.day.value);\n        if (!selects.year.value || !selects.month.value || !selects.day.value) {\n          original.value = \'\';\n          detail.textContent = \'請依序選擇民國年、月、日\';\n        } else {\n          const mm = String(month).padStart(2, \'0\'), dd = String(day).padStart(2, \'0\');\n          original.value = year >= 1912\n            ? String(year - 1911).padStart(2, \'0\') + mm + dd\n            : `${year}-${mm}-${dd}`;\n          detail.textContent = `已選擇：${rocYearLabel(year)} 年 ${month} 月 ${day} 日`;\n        }\n        original.dispatchEvent(new Event(\'input\', {bubbles:true}));\n        validateBirthday(selects);\n      }\n      selects.year.addEventListener(\'change\', () => {months(); days(); update();});\n      selects.month.addEventListener(\'change\', () => {days(); update();});\n      selects.day.addEventListener(\'change\', update);\n\n      function parse(raw) {\n        const value = String(raw || \'\').trim();\n        const western = /^(\\d{4})[-/](\\d{1,2})[-/](\\d{1,2})$/.exec(value);\n        if (western) return western.slice(1).map(Number);\n        const roc = /^(\\d{2,3})(\\d{2})(\\d{2})$/.exec(value);\n        return roc ? [1911 + Number(roc[1]), Number(roc[2]), Number(roc[3])] : null;\n      }\n      const old = parse(previous);\n      if (old && years.some(item => item[0] === old[0])) {\n        selects.year.value = String(old[0]);\n        months();\n        selects.month.value = String(old[1]);\n        days();\n        selects.day.value = String(old[2]);\n        if (selects.year.value && selects.month.value && selects.day.value) {\n          const mm = String(old[1]).padStart(2,\'0\'), dd = String(old[2]).padStart(2,\'0\');\n          original.value = old[0] >= 1912\n            ? String(old[0] - 1911).padStart(2,\'0\') + mm + dd\n            : `${old[0]}-${mm}-${dd}`;\n          detail.textContent = `已選擇：${rocYearLabel(old[0])} 年 ${old[1]} 月 ${old[2]} 日`;\n        } else original.value = \'\';\n      } else original.value = \'\';\n      return {holder, selects};\n    }\n\n    const picker=createBirthdayPicker();\n    validateBirthday(picker.selects);\n  }\n  // Deferred scripts run while readyState is interactive, before legacy form prefill.\n  if(document.readyState!==\'complete\')document.addEventListener(\'DOMContentLoaded\',init,{once:true});\n  else init();\n})();\n'


def shared_html(raw):
    html = raw.decode('utf-8')
    # Only remove the local synthetic form guard; original captcha/booking scripts stay.
    html, removed = re.subn(r'<script\b[^>]*\bid="shanlin-patient-field-validation"[^>]*>.*?</script>',
                            '', html, flags=re.S | re.I)
    if removed > 1:
        raise ValueError('unexpected repeated local form guard')
    html, count = re.subn(r'(<head\b[^>]*>)', lambda m:m[1] + BOOTSTRAP, html,
                          count=1, flags=re.I)
    if count != 1:
        raise ValueError('missing page head')
    if 'id="bookingForm"' in html:
        if removed != 1 or html.count('</body>') != 1:
            raise ValueError('unexpected local booking form')
        html = html.replace('</body>', '<script id="shanlin-shared-birthday-picker">' + BIRTHDAY + '</script></body>', 1)
    return html.encode('utf-8')


class SharedBooking:
    def __init__(self, original):
        self.original = original

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.original(scope, receive, send)
        path, method = scope['path'], scope['method']
        query = parse_qs(scope.get('query_string', b'').decode('ascii', errors='replace'))
        clinic = query.get('clinic', [None])
        selected = clinic == ['shanlin']
        target = readable(path) and method == 'GET' and selected
        writing = path == CONFIRM
        health = path == '/api/shanlin/shared-booking-status'
        headers = {k.decode('latin1').lower():v.decode('latin1') for k,v in scope.get('headers', [])}
        client = (scope.get('client') or ('',0))[0]
        host = headers.get('host','').split(':',1)[0]
        local = client in LOCAL and host in LOCAL
        if target or writing or health:
            if not local:
                return await JSONResponse({'detail':'僅可從本機網站使用共用預約入口'},403,headers=HEADERS)(scope,receive,send)
            if health:
                if method != 'GET':
                    return await JSONResponse({'detail':'method not allowed'},405,headers=HEADERS)(scope,receive,send)
                return await JSONResponse({'clinicId':'shanlin','mode':'shared-online',
                    'bookingOrigin':ONLINE,'writesToIsolated8018':False},headers=HEADERS)(scope,receive,send)
            if writing:
                origin = headers.get('origin','').rstrip('/')
                expected_origin = scope.get('scheme','http') + '://' + headers.get('host','')
                token = headers.get('x-doubts-patient-test-page','')
                fetch_site = headers.get('sec-fetch-site','')
                if (method != 'POST' or not selected or origin != expected_origin or
                        fetch_site not in ('','same-origin') or not token or
                        not hmac.compare_digest(token,legacy.PAGE_TOKEN)):
                    return await JSONResponse({'detail':'預約頁驗證失敗，請重新整理頁面'},403,headers=HEADERS)(scope,receive,send)
                if not headers.get('content-type','').lower().startswith('application/json'):
                    return await JSONResponse({'detail':'僅接受 JSON'},415,headers=HEADERS)(scope,receive,send)
                body = b''
                while True:
                    part = await receive()
                    if part['type'] == 'http.disconnect': return
                    body += part.get('body',b'')
                    if len(body)>MAX_REQUEST:
                        return await JSONResponse({'detail':'預約資料過長'},413,headers=HEADERS)(scope,receive,send)
                    if not part.get('more_body'): break
                try:
                    value = json.loads(body)
                    if not isinstance(value,dict) or value.get('plan') not in ('A','B','C','SELF_PAY'):
                        raise ValueError()
                    if value.get('clinicId','shanlin') != 'shanlin':raise ValueError()
                except (ValueError,UnicodeError):
                    return await JSONResponse({'detail':'山林預約資料格式不正確'},422,headers=HEADERS)(scope,receive,send)
                status, answer = await run_in_threadpool(upstream,'POST','/api/booking/confirm','',body)
            else:
                safe_query = {k:v for k,v in query.items() if k != 'clinic'}
                status, answer = await run_in_threadpool(upstream,'GET',path,urlencode(safe_query,doseq=True),None)
            return await JSONResponse(answer,status_code=status,headers=HEADERS)(scope,receive,send)
        if path not in PAGES or method != 'GET' or not local or not selected:
            return await self.original(scope,receive,send)
        messages=[]
        async def capture(message):messages.append(message)
        await self.original(scope,receive,capture)
        start=next((m for m in messages if m['type']=='http.response.start'),None)
        content_type=dict(start.get('headers',[])).get(b'content-type',b'') if start else b''
        if start and start['status']==200 and b'text/html' in content_type:
            raw=b''.join(m.get('body',b'') for m in messages if m['type']=='http.response.body')
            try:changed=shared_html(raw)
            except (UnicodeError,ValueError):
                return await JSONResponse({'detail':'共用預約頁版本不符，請先檢查程式版本'},503,headers=HEADERS)(scope,receive,send)
            kept={k.decode('latin1'):v.decode('latin1') for k,v in start.get('headers',[])
                  if k.lower() not in (b'content-length',b'content-type',b'etag',b'last-modified')}
            kept.update(HEADERS)
            return await Response(changed,media_type='text/html',headers=kept)(scope,receive,send)
        for message in messages:await send(message)


app = SharedBooking(legacy.app)
