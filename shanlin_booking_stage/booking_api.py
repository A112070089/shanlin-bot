"""8018 API: import the EXISTING Shanlin backend but expose only test transactions.

Start: uvicorn booking_api:app --host 127.0.0.1 --port 8018
No LIVE patients, LINE, reminders, Excel writes or legacy admin endpoints.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import threading
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from shanlin_v363_readonly import (
    check_staging_configuration, read_source, _authorize as authorize_read,
    ROUTE as SUMMARY_PATH, LOCAL_HOSTS, SAFE_RESPONSE_HEADERS,
)
from booking_transactions import BookingStore

# The test-only Firebase hostname and credential project are validated before
# the original main.py can initialize an app.
check_staging_configuration()
import main as shanlin  # Existing Shanlin code and firebase_admin.db source.

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
PATH = '/api/integration/v365/appointments'
HEADERS = dict(SAFE_RESPONSE_HEADERS)
NONCE = re.compile(r'[A-Za-z0-9_-]{24,100}\Z')
_seen: dict[str,float] = {}
_lock = threading.Lock()


def _secret() -> bytes:
    # Independent review flag: enabling v3.6.3 READ does not enable WRITES.
    if os.getenv('SHANLIN_V365_SYNTHETIC_WRITE_ENABLED') != '1':
        raise HTTPException(423, 'test-only transactional booking writes disabled')
    val = os.getenv('SHANLIN_V363_SERVICE_SECRET','')
    if len(val) < 40 or '\r' in val or '\n' in val:
        raise HTTPException(503, 'test-only service authentication missing')
    return val.encode()


def _local(request: Request):
    if (request.client is None or request.client.host not in LOCAL_HOSTS
            or request.url.hostname not in LOCAL_HOSTS):
        raise HTTPException(403, 'localhost-only test application')


def _verify(request: Request, body: bytes):
    _local(request)
    secret = _secret()
    stamp = request.headers.get('X-DOUBTS-Timestamp','')
    nonce = request.headers.get('X-DOUBTS-Nonce','')
    sig = request.headers.get('X-DOUBTS-Signature','')
    if (not stamp.isascii() or not stamp.isdecimal() or len(stamp)!=10
            or not NONCE.fullmatch(nonce) or not re.fullmatch(r'[0-9a-f]{64}\Z',sig)):
        raise HTTPException(401, 'invalid test service signature')
    now = time.time()
    if abs(now-int(stamp))>60: raise HTTPException(401, 'expired test request')
    digest = hashlib.sha256(body).hexdigest()
    message = f'{request.method}\n{request.url.path}\n{stamp}\n{nonce}\n{digest}'.encode()
    if not hmac.compare_digest(sig,hmac.new(secret,message,hashlib.sha256).hexdigest()):
        raise HTTPException(401, 'invalid test service signature')
    with _lock:
        for item,deadline in list(_seen.items()):
            if deadline < now: del _seen[item]
        if nonce in _seen: raise HTTPException(409,'replayed test request')
        if len(_seen)>2000: raise HTTPException(503, 'test replay cache full')
        _seen[nonce] = now+125


async def _payload(request: Request):
    body = await request.body()
    if len(body)>8192: raise HTTPException(413,'test request too large')
    _verify(request,body)
    if not request.headers.get('content-type','').lower().startswith('application/json'):
        raise HTTPException(415,'only JSON accepted')
    try: value=json.loads(body)
    except (ValueError,UnicodeError): raise HTTPException(422,'invalid JSON') from None
    if not isinstance(value,dict): raise HTTPException(422,'expected one JSON object')
    return value


@app.get(SUMMARY_PATH, include_in_schema=False)
def existing_summary(request: Request):
    _local(request)
    authorize_read(request)
    return JSONResponse(read_source(shanlin.db),headers=HEADERS)


@app.get(PATH, include_in_schema=False)
def list_bookings(request: Request):
    _verify(request,b'')
    return JSONResponse(BookingStore(shanlin.db).list(),headers=HEADERS)


@app.post(PATH, include_in_schema=False)
async def create_booking(request: Request):
    data=await _payload(request)
    return JSONResponse(BookingStore(shanlin.db).change('create',data),headers=HEADERS)


@app.patch(PATH+'/{key}', include_in_schema=False)
async def update_booking(key: str,request: Request):
    data=await _payload(request)
    return JSONResponse(BookingStore(shanlin.db).change('update',data,key),headers=HEADERS)


@app.delete(PATH+'/{key}', include_in_schema=False)
async def cancel_booking(key: str,request: Request):
    data=await _payload(request)
    if set(data) != {'expectedRevision'}: raise HTTPException(422,'cancellation fields not allowed')
    return JSONResponse(BookingStore(shanlin.db).change('cancel',data,key),headers=HEADERS)
