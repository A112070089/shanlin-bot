"""Existing DOUBTS clinic session -> original Shanlin test DB transactional adapter.

Only Shanlin's verified clinic session can view or mutate synthetic test data;
ENGINEER platform sessions and Yidian sessions cannot access patient-shaped rows.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request as UrlRequest, build_opener

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

import pilot_backend as backend
from platform_console import local_only, NO_CACHE

router = APIRouter()
API_ROOT = '/api/pilot/admin/shanlin/booking-stage'
UPSTREAM_ROOT = 'http://127.0.0.1:8018/api/integration/v365/appointments'
HEADERS = {**NO_CACHE, 'Pragma':'no-cache'}
PAGE = Path(__file__).resolve().parent / 'shanlin_admin_booking_stage.html'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None


def _shanlin_session(request, sess):
    local_only(request)
    if (sess.get('clinic') != 'shanlin' or sess.get('role') != 'clinic_admin'
            or not isinstance(sess.get('legacyConfig'),dict)
            or sess['legacyConfig'].get('name') != '山林診所'):
        raise HTTPException(403,'僅限完成正式山林身分驗證的診所管理員')
    if os.getenv('PILOT_V365_SYNTHETIC_BOOKINGS_ENABLED') != '1':
        raise HTTPException(423, '測試預約管理未開放')
    return sess


def _post_check(request):
    # Same-origin mutations require both the original pilot CSRF and Origin.
    if request.headers.get('origin','').rstrip('/') != str(request.base_url).rstrip('/'):
        raise HTTPException(403,'僅可從本機公版頁面執行預約操作')


def _relay(method, remainder='', payload=None):
    val=os.getenv('PILOT_V363_SERVICE_SECRET','')
    if len(val)<40 or '\r' in val or '\n' in val:
        raise HTTPException(503,'隔離服務金鑰尚未設定')
    if remainder and (not remainder.startswith('/') or '/' in remainder[1:]
                      or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-' for c in remainder[1:])):
        raise HTTPException(422, '測試預約識別碼不正確')
    path='/api/integration/v365/appointments'+remainder
    body=(json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
          if payload is not None else b'')
    if len(body)>8192:raise HTTPException(413,'預約資料超出安全上限')
    ts=str(int(time.time()))
    nonce=secrets.token_urlsafe(28)
    digest=hashlib.sha256(body).hexdigest()
    mac=hmac.new(val.encode(),f'{method}\n{path}\n{ts}\n{nonce}\n{digest}'.encode(),hashlib.sha256).hexdigest()
    req=UrlRequest(UPSTREAM_ROOT+remainder,data=body if payload is not None else None,
                   method=method,headers={'Accept':'application/json','Content-Type':'application/json',
                      'X-DOUBTS-Timestamp':ts,'X-DOUBTS-Nonce':nonce,'X-DOUBTS-Signature':mac})
    try:
        with build_opener(ProxyHandler({}),NoRedirect()).open(req,timeout=4) as response:
            if response.status < 200 or response.status >= 300: raise ValueError('unexpected status')
            data=response.read(256*1024+1)
            if len(data)>256*1024:raise ValueError('unexpected response length')
            value=json.loads(data)
    except HTTPError as exc:
        if exc.code in (401,403,409,422,423,428):
            # No upstream raw error content is copied into the clinic UI.
            status=exc.code
            message={401:'後端簽章驗證失敗',403:'拒絕不安全請求',409:'名額或資料版本衝突，請重新載入',
                     422:'預約資料格式不正確',423:'測試寫入尚未開放',428:'請重新載入最新版預約資料'}[status]
            raise HTTPException(status,message) from None
        raise HTTPException(503,'山林隔離預約服務暫時無法使用') from None
    except (OSError,URLError,ValueError,UnicodeError,TimeoutError):
        raise HTTPException(503,'無法連線山林隔離預約服務；未觸及正式資料') from None
    if not isinstance(value,dict) or value.get('clinicId')!='shanlin' or value.get('isSynthetic') is not True:
        raise HTTPException(503,'測試服務身分不符，已拒絕輸出資料')
    return value


@router.get('/pilot/shanlin/booking-stage', include_in_schema=False)
def stage_page(request: Request):
    local_only(request)
    return FileResponse(PAGE,media_type='text/html',headers={**HEADERS,
       'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; img-src 'none'; form-action 'none'; frame-ancestors 'none'"})


@router.get(API_ROOT+'/appointments', include_in_schema=False)
def list_bookings(request:Request,sess=Depends(backend.require_clinic)):
    _shanlin_session(request,sess)
    return JSONResponse(_relay('GET'),headers=HEADERS)


@router.post(API_ROOT+'/appointments', include_in_schema=False)
def add_booking(request:Request, body:dict,sess=Depends(backend.require_clinic_mutation)):
    _shanlin_session(request,sess);_post_check(request)
    return JSONResponse(_relay('POST',payload=body),headers=HEADERS)


@router.patch(API_ROOT+'/appointments/{key}', include_in_schema=False)
def edit_booking(request:Request,key:str,body:dict,sess=Depends(backend.require_clinic_mutation)):
    _shanlin_session(request,sess);_post_check(request)
    return JSONResponse(_relay('PATCH','/'+key,payload=body),headers=HEADERS)


@router.delete(API_ROOT+'/appointments/{key}', include_in_schema=False)
def cancel_booking(request:Request,key:str,body:dict,sess=Depends(backend.require_clinic_mutation)):
    _shanlin_session(request,sess);_post_check(request)
    return JSONResponse(_relay('DELETE','/'+key,payload=body),headers=HEADERS)
