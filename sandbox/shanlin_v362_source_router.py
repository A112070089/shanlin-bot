"""v3.6.2: reusable Shanlin-only read-side producer. DISABLED by default.

Designed to be included by a vetted Shanlin FastAPI app in a future release.
This package never reads Firebase; a trusted application must inject a loader.
The shipped demo supplies only synthetic rows. NEVER expose this demo publicly.
"""
from __future__ import annotations
from collections import Counter
from datetime import date
import hashlib
import hmac
import os
import re
import secrets
import threading
import time
from typing import Callable
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

PATH = '/api/integration/v362/booking-summary'
TAG = 'DOUBTS-SHANLIN-V362-SYNTHETIC'
HEADERS = {'Cache-Control': 'no-store, private', 'Pragma': 'no-cache'}
_NONCE = re.compile(r'[A-Za-z0-9_-]{20,100}\Z')
_DATE = re.compile(r'\d{4}-\d{2}-\d{2}\Z')
_TIME = re.compile(r'(?:[01]\d|2[0-3]):[0-5]\d\Z')
_VALID_PLAN = {'A', 'B', 'C', 'SELF_PAY', 'OTHER'}
_nonce_lock = threading.Lock()
_seen: dict[str, float] = {}


def _settings() -> bytes:
    if os.getenv('SHANLIN_V362_SYNTHETIC_ONLY') != '1':
        raise HTTPException(423, 'read-side integration is disabled')
    secret = os.getenv('SHANLIN_V362_SERVICE_SECRET', '')
    if len(secret) < 40 or any(c in secret for c in '\r\n'):
        raise HTTPException(503, 'service-to-service authentication not configured')
    return secret.encode('utf-8')


def signature(secret: bytes, stamp: str, nonce: str) -> str:
    message = f'GET\n{PATH}\n{stamp}\n{nonce}'.encode('ascii')
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def verify_request(request: Request) -> None:
    secret = _settings()
    # In the synthetic test this router is strictly localhost-only.
    if request.client is None or request.client.host not in ('127.0.0.1', '::1', 'testclient'):
        raise HTTPException(403, 'localhost synthetic source only')
    stamp = request.headers.get('x-doubts-timestamp', '')
    nonce = request.headers.get('x-doubts-nonce', '')
    given = request.headers.get('x-doubts-signature', '')
    if not stamp.isascii() or not stamp.isdecimal() or len(stamp) not in (10, 11):
        raise HTTPException(401, 'invalid authentication timestamp')
    if not _NONCE.fullmatch(nonce) or not re.fullmatch(r'[0-9a-f]{64}\Z', given):
        raise HTTPException(401, 'invalid service signature')
    now = time.time()
    if abs(now - int(stamp)) > 75:
        raise HTTPException(401, 'expired service authentication')
    expected = signature(secret, stamp, nonce)
    if not hmac.compare_digest(given, expected):
        raise HTTPException(401, 'invalid service signature')
    # In-memory nonce guard suitable for single-process *local sandbox* only.
    # Production rollout requires shared replay storage or mTLS/proxy auth.
    with _nonce_lock:
        for key, expiry in list(_seen.items()):
            if expiry < now:
                _seen.pop(key, None)
        if nonce in _seen:
            raise HTTPException(409, 'replayed signed request')
        if len(_seen) >= 2000:
            raise HTTPException(503, 'replay window capacity exceeded')
        _seen[nonce] = now + 155


def _safe_date(obj: object) -> str | None:
    if not isinstance(obj, str) or not _DATE.fullmatch(obj):
        return None
    try:
        date.fromisoformat(obj)
    except ValueError:
        return None
    return obj


def _safe_time(obj: object) -> str | None:
    return obj if isinstance(obj, str) and _TIME.fullmatch(obj) else None


def summarize_synthetic_rows(rows: object) -> dict:
    """One-way aggregate: NO patient fields or IDs are copied or forwarded."""
    if not isinstance(rows, (list, tuple)) or len(rows) > 1000:
        raise HTTPException(503, 'source row count/shape invalid')
    by_slot = Counter()
    by_plan = Counter()
    by_kind = Counter()
    for row in rows:
        if not isinstance(row, dict):
            raise HTTPException(503, 'source row shape invalid')
        is_selfpay = row.get('_pureSelfPay') is True
        kind = 'self_pay_only' if is_selfpay else 'checkup'
        by_kind[kind] += 1
        plan = 'SELF_PAY' if is_selfpay else str(row.get('plan') or '').strip().upper()
        plan = plan if plan in _VALID_PLAN else 'OTHER'
        by_plan[plan] += 1
        d = _safe_date(row.get('selfPayDate') if is_selfpay else row.get('date'))
        t = _safe_time(row.get('selfPayTime') if is_selfpay else row.get('time'))
        if d is not None and t is not None:
            by_slot[(d, t)] += 1
    return {
        'sourceTag': TAG,
        'clinicId': 'shanlin',
        'mode': 'synthetic_only',
        'isSynthetic': True,
        'containsPatientIdentity': False,
        'bookingWritesEnabled': False,
        'capacityVerified': False,
        'remindersEnabled': False,
        'count': len(rows),
        'byPlan': [{'plan': p, 'count': n} for p, n in sorted(by_plan.items())],
        'byKind': [{'kind': k, 'count': n} for k, n in sorted(by_kind.items())],
        'slotCounts': [
            {'date': d, 'time': t, 'bookedCount': n,
             'capacity': None, 'availabilityConfirmed': False}
            for (d, t), n in sorted(by_slot.items())
        ],
    }


def create_router(rows_loader: Callable[[], object]) -> APIRouter:
    router = APIRouter()

    @router.get(PATH, include_in_schema=False)
    def read_summary(request: Request):
        verify_request(request)
        result = summarize_synthetic_rows(rows_loader())
        return JSONResponse(result, headers=HEADERS)

    return router
