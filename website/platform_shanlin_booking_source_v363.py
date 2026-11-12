"""v3.6.3 DOUBTS read-only CLIENT for the staged ORIGINAL Shanlin app.

Fixed localhost URL; no real Railway/API credentials; never accepts raw patient rows.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from urllib.error import URLError, HTTPError

from fastapi import HTTPException
from platform_shanlin_booking_source_v362 import _validate as validate_v362

ENDPOINT = 'http://127.0.0.1:8018/api/integration/v363/booking-summary'
PATH = '/api/integration/v363/booking-summary'
TAG = 'DOUBTS-SHANLIN-V363-EXISTING-APP-TEST'
MODE = 'shanlin_app_test_database'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _secret() -> bytes:
    if os.getenv('PILOT_V363_TEST_READ_ENABLED') != '1':
        raise HTTPException(423, 'v3.6.3 test integration disabled')
    val = os.getenv('PILOT_V363_SERVICE_SECRET', '')
    if len(val) < 40 or '\r' in val or '\n' in val:
        raise HTTPException(503, 'dedicated read-only test authentication not configured')
    return val.encode('utf-8')


def validate(payload: object) -> dict:
    if not isinstance(payload, dict) or payload.get('sourceTag') != TAG or payload.get('mode') != MODE:
        raise HTTPException(503, 'unexpected Shanlin test backend identity')
    converted = dict(payload)
    converted['sourceTag'] = 'DOUBTS-SHANLIN-V362-SYNTHETIC'
    converted['mode'] = 'synthetic_only'
    validate_v362(converted)  # full strict allowlist/count/PII/slot contract
    return {key: payload[key] for key in sorted(payload)}


def read_test_backend_summary() -> dict:
    secret = _secret()
    stamp = str(int(time.time()))
    nonce = secrets.token_urlsafe(28)
    sig = hmac.new(secret, f'GET\n{PATH}\n{stamp}\n{nonce}'.encode('ascii'),
                   hashlib.sha256).hexdigest()
    req = Request(ENDPOINT, method='GET', headers={
        'Accept':'application/json', 'X-DOUBTS-Timestamp':stamp,
        'X-DOUBTS-Nonce':nonce, 'X-DOUBTS-Signature':sig,
    })
    try:
        with build_opener(ProxyHandler({}),NoRedirect()).open(req,timeout=3) as resp:
            if resp.status != 200:
                raise ValueError('status')
            body = resp.read(32769)
            if len(body) > 32768:
                raise ValueError('response too large')
            result = json.loads(body.decode('utf-8'))
        return validate(result)
    except (HTTPError, URLError, OSError, ValueError, UnicodeError, TimeoutError):
        raise HTTPException(503, 'Shanlin test backend unavailable; no production data accessed') from None


def contract() -> dict:
    return {
        'version':'v3.6.3', 'source':'original_shanlin_app_staged_copy',
        'clinicId':'shanlin', 'fixedEndpoint':PATH,
        'writesEnabled':False, 'productionReadEnabled':False,
        'individualStaffRolesVerified':False,
        'dataAccess':'independent synthetic TEST Firebase only; no live patient records',
        'note':'No original Shanlin GitHub/Railway application was modified.',
    }
