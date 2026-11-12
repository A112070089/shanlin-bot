"""DOUBTS v3.6.3: test-only signed read-side router for the EXISTING Shanlin FastAPI app.

Reads the original Shanlin nodes through the original firebase_admin.db object. The
module is deliberately impossible to enable against the known production Firebase.
No raw rows or private patient fields leave this module. Not production-ready.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

ROUTE = '/api/integration/v363/booking-summary'
TAG = 'DOUBTS-SHANLIN-V363-EXISTING-APP-TEST'
MODE = 'shanlin_app_test_database'
PROD_FIREBASE = 'shanlin-clinic-default-rtdb.firebaseio.com'
LOCAL_HOSTS = frozenset({'127.0.0.1', '::1', 'localhost', 'testclient', 'testserver'})
SAFE_RESPONSE_HEADERS = {
    'Cache-Control': 'no-store, private', 'Pragma': 'no-cache',
    'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
}
_NONCE_RE = re.compile(r'[A-Za-z0-9_-]{24,100}\Z')
_DATE_RE = re.compile(r'\d{4}-\d{2}-\d{2}\Z')
_TIME_RE = re.compile(r'(?:[01]\d|2[0-3]):[0-5]\d\Z')
_seen: dict[str, float] = {}
_seen_lock = threading.Lock()


def check_staging_configuration() -> str:
    """Fail before importing the old Shanlin app, which initializes Firebase."""
    if os.getenv('SHANLIN_V363_STAGING_ENABLED') != '1':
        raise RuntimeError('v3.6.3 staging is disabled')
    fb = os.getenv('FIREBASE_URL', '')
    target = os.getenv('SHANLIN_V363_TEST_FIREBASE_HOST', '').strip().lower()
    parsed = urlsplit(fb)
    if (parsed.scheme != 'https' or not target or parsed.hostname != target
            or parsed.username or parsed.password or parsed.port is not None
            or parsed.path not in ('', '/') or parsed.query or parsed.fragment
            or not target.endswith(('.firebaseio.com', '.firebasedatabase.app'))
            or not any(part in target for part in ('test', 'staging', 'sandbox', 'dev'))
            or target == PROD_FIREBASE):
        raise RuntimeError('only an explicitly pinned, independent TEST Firebase is permitted')
    creds = os.getenv('FIREBASE_CREDENTIALS', '')
    if creds and creds != '{}':
        try:
            service = json.loads(creds)
        except (ValueError, TypeError) as exc:
            raise RuntimeError('invalid test Firebase service-account declaration') from exc
        expected_project = os.getenv('SHANLIN_V363_TEST_PROJECT_ID', '').strip()
        if (not isinstance(service, dict) or service.get('type') != 'service_account'
                or not expected_project or service.get('project_id') != expected_project
                or not any(k in expected_project.lower() for k in ('test', 'staging', 'sandbox', 'dev'))):
            raise RuntimeError('only the explicit test Firebase service-account project is accepted')
    return target


def _service_secret() -> bytes:
    if os.getenv('SHANLIN_V363_READ_ENABLED') != '1':
        raise HTTPException(423, 'test read integration disabled')
    val = os.getenv('SHANLIN_V363_SERVICE_SECRET', '')
    if len(val) < 40 or '\n' in val or '\r' in val:
        raise HTTPException(503, 'dedicated test service authentication not configured')
    return val.encode('utf-8')


def make_signature(secret: bytes, stamp: str, nonce: str) -> str:
    return hmac.new(secret, f'GET\n{ROUTE}\n{stamp}\n{nonce}'.encode('ascii'), hashlib.sha256).hexdigest()


def _authorize(req: Request) -> None:
    _service_secret()
    if (req.client is None or req.client.host not in LOCAL_HOSTS
            or req.url.hostname not in LOCAL_HOSTS):
        raise HTTPException(403, 'local test only')
    stamp = req.headers.get('x-doubts-timestamp', '')
    nonce = req.headers.get('x-doubts-nonce', '')
    sig = req.headers.get('x-doubts-signature', '')
    if (not stamp.isascii() or not stamp.isdecimal() or len(stamp) != 10
            or not _NONCE_RE.fullmatch(nonce) or not re.fullmatch(r'[0-9a-f]{64}\Z', sig)):
        raise HTTPException(401, 'invalid test service authentication')
    now = time.time()
    if abs(now - int(stamp)) > 60:
        raise HTTPException(401, 'expired test service authentication')
    if not hmac.compare_digest(sig, make_signature(_service_secret(), stamp, nonce)):
        raise HTTPException(401, 'invalid test service authentication')
    with _seen_lock:
        for n, expiry in list(_seen.items()):
            if expiry < now:
                del _seen[n]
        if nonce in _seen:
            raise HTTPException(409, 'replayed test service request')
        if len(_seen) >= 2000:
            raise HTTPException(503, 'test replay cache full')
        _seen[nonce] = now + 125


def _read_dict(db, name: str) -> dict:
    try:
        value = db.reference(name).get()
    except Exception:
        raise HTTPException(503, 'test Shanlin database unavailable') from None
    if value is None:
        return {}
    if not isinstance(value, dict) or len(value) > 1000:
        raise HTTPException(503, 'unexpected test Shanlin data shape')
    return value


def _phone(s: object) -> str:
    s = str(s or '').strip()
    return ('0' + s) if s and not s.startswith('0') else s


def _unique_lookup(rows: dict, field: str, transform=str) -> dict[str, str]:
    index: dict[str, str] = {}
    ambiguous: set[str] = set()
    for key, rec in rows.items():
        if not isinstance(rec, dict):
            raise HTTPException(503, 'unexpected self-pay record shape')
        val = transform(rec.get(field) or '')
        if val:
            if val in index: ambiguous.add(val)
            else: index[val] = key
    for val in ambiguous:
        index.pop(val, None)
    return index


def _check_tenant(record: dict):
    if record.get('clinicId') not in (None, 'shanlin'):
        raise HTTPException(409, 'clinic record ownership mismatch')
    if record.get('doubtsSyntheticV363') is not True:
        raise HTTPException(409, 'unverified synthetic record; refusing patient data access')


def _date_time(d: object, t: object) -> tuple[str, str] | None:
    if not isinstance(d, str) or not _DATE_RE.fullmatch(d):
        return None
    try: date.fromisoformat(d)
    except ValueError: return None
    if not isinstance(t, str) or not _TIME_RE.fullmatch(t):
        return None
    return d, t


def summarize_original_nodes(appointments: dict, selfpay: dict) -> dict:
    """Derived from Shanlin legacy admin's matching rules; no raw identifiers emitted.

    Pure-selfpay records matched to a checkup are counted only once. This is
    a record tally, NOT a verified count of active bookings or slot capacity.
    """
    if not isinstance(appointments, dict) or not isinstance(selfpay, dict):
        raise HTTPException(503, 'unexpected Shanlin source nodes')
    if len(appointments) > 1000 or len(selfpay) > 1000:
        raise HTTPException(503, 'test source too large')
    id_index = _unique_lookup(selfpay, 'idNumber', lambda v: str(v).strip().upper())
    phone_index = _unique_lookup(selfpay, 'phone', _phone)
    claimed: set[str] = set()
    aggregate: list[dict] = []
    for key, data in appointments.items():
        if not isinstance(data, dict):
            raise HTTPException(503, 'unexpected checkup record shape')
        _check_tenant(data)
        sp_key = None
        if isinstance(selfpay.get(key), dict):
            sp_key = key
        else:
            appt_id = str(data.get('idNumber') or '').strip().upper()
            appt_phone = _phone(data.get('phone'))
            if appt_id and appt_id in id_index:
                sp_key = id_index[appt_id]
            elif appt_phone and appt_phone in phone_index:
                sp_key = phone_index[appt_phone]
        if sp_key is not None:
            if sp_key in claimed:
                raise HTTPException(409, 'ambiguous self-pay linkage')
            _check_tenant(selfpay[sp_key])
            claimed.add(sp_key)
        aggregate.append({'plan': data.get('plan'), 'date': data.get('date'),
                          'time': data.get('time'), '_pureSelfPay': False})
    for key, item in selfpay.items():
        if not isinstance(item, dict):
            raise HTTPException(503, 'unexpected self-pay record shape')
        _check_tenant(item)
        if key in claimed:
            continue
        aggregate.append({'plan': 'SELF_PAY', 'selfPayDate': item.get('selfPayDate'),
                          'selfPayTime': item.get('selfPayTime'), '_pureSelfPay': True})
    if len(aggregate) > 1000:
        raise HTTPException(503, 'too many test records')
    by_plan = Counter()
    by_kind = Counter()
    by_slot = Counter()
    for row in aggregate:
        pure = row['_pureSelfPay'] is True
        kind = 'self_pay_only' if pure else 'checkup'
        plan = 'SELF_PAY' if pure else str(row.get('plan') or '').strip().upper()
        if plan not in ('A', 'B', 'C', 'SELF_PAY', 'OTHER'):
            plan = 'OTHER'
        by_plan[plan] += 1
        by_kind[kind] += 1
        when = _date_time(row.get('selfPayDate') if pure else row.get('date'),
                          row.get('selfPayTime') if pure else row.get('time'))
        if when:
            by_slot[when] += 1
    return {
        'clinicId': 'shanlin', 'sourceTag': TAG, 'mode': MODE, 'isSynthetic': True,
        'containsPatientIdentity': False, 'bookingWritesEnabled': False,
        'capacityVerified': False, 'remindersEnabled': False, 'count': len(aggregate),
        'byPlan': [{'plan': p, 'count': n} for p,n in sorted(by_plan.items())],
        'byKind': [{'kind': k, 'count': n} for k,n in sorted(by_kind.items())],
        'slotCounts': [{'date': d, 'time': t, 'bookedCount': n,
                        'capacity': None, 'availabilityConfirmed': False}
                       for (d,t),n in sorted(by_slot.items())],
    }


def read_source(db) -> dict:
    check_staging_configuration()
    clinic = _read_dict(db, 'booking_config/clinic')
    if (clinic.get('clinicId') != 'shanlin' or clinic.get('name') != '山林診所'
            or clinic.get('integrationV363TestOnly') is not True):
        raise HTTPException(409, 'test clinic provenance not confirmed')
    appointments = _read_dict(db, 'appointments')
    selfpay = _read_dict(db, 'self_pay_booking')
    return summarize_original_nodes(appointments, selfpay)


def attach_staging_router(app, db):
    """Called only in a pinned local copy of the original Shanlin main.py."""
    check_staging_configuration()
    router = APIRouter()

    @router.get(ROUTE, include_in_schema=False)
    def summary(request: Request):
        _authorize(request)
        return JSONResponse(read_source(db), headers=SAFE_RESPONSE_HEADERS)

    # The original app's routes exist in the staging copy, but are all blocked.
    # This prevents any LINE webhook, admin mutation or booking submission.
    @app.middleware('http')
    async def staging_readonly_firewall(request: Request, call_next):
        if request.url.path != ROUTE:
            return JSONResponse({'detail':'v3.6.3 staging is read-only'}, status_code=404,
                                headers=SAFE_RESPONSE_HEADERS)
        if request.method != 'GET':
            return JSONResponse({'detail':'read-only route'}, status_code=405,
                                headers=SAFE_RESPONSE_HEADERS)
        if (request.client is None or request.client.host not in LOCAL_HOSTS
                or request.url.hostname not in LOCAL_HOSTS):
            return JSONResponse({'detail':'localhost staging only'}, status_code=403,
                                headers=SAFE_RESPONSE_HEADERS)
        return await call_next(request)

    app.include_router(router)
    return app
