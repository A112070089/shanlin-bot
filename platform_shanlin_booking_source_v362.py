"""v3.6.2 backend-to-backend local synthetic summary; no patient data on wire."""
from __future__ import annotations
import hmac
import hashlib
import json
import os
import re
import secrets
import time
from urllib.error import URLError, HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from fastapi import HTTPException

ENDPOINT = 'http://127.0.0.1:8017/api/integration/v362/booking-summary'
PATH = '/api/integration/v362/booking-summary'
SOURCE_TAG = 'DOUBTS-SHANLIN-V362-SYNTHETIC'
_TOP = frozenset({'sourceTag','clinicId','mode','isSynthetic','containsPatientIdentity',
                 'bookingWritesEnabled','capacityVerified','remindersEnabled','count',
                 'byPlan','byKind','slotCounts'})
_PLAN_KEYS = frozenset({'plan','count'})
_KIND_KEYS = frozenset({'kind','count'})
_SLOT_KEYS = frozenset({'date','time','bookedCount','capacity','availabilityConfirmed'})

class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _secret() -> bytes:
    if os.environ.get('PILOT_V362_SYNTHETIC_READ_ENABLED') != '1':
        raise HTTPException(423, 'v3.6.2 synthetic read source disabled')
    secret = os.environ.get('PILOT_V362_SERVICE_SECRET', '')
    if len(secret) < 40 or any(c in secret for c in '\r\n'):
        raise HTTPException(503, 'v3.6.2 service authentication not configured')
    return secret.encode('utf-8')


def _count(value: object) -> bool:
    return type(value) is int and 0 <= value <= 1000


def _validate(payload: object) -> dict:
    if not isinstance(payload, dict) or set(payload) != _TOP:
        raise HTTPException(503, 'source contract mismatch')
    if (payload['sourceTag'] != SOURCE_TAG or payload['clinicId'] != 'shanlin'
            or payload['mode'] != 'synthetic_only' or payload['isSynthetic'] is not True
            or payload['containsPatientIdentity'] is not False
            or payload['bookingWritesEnabled'] is not False
            or payload['capacityVerified'] is not False
            or payload['remindersEnabled'] is not False
            or not _count(payload['count'])):
        raise HTTPException(503, 'source identity or security contract invalid')
    total = payload['count']
    def valid_entries(key, keys, accepted, value_name):
        entries = payload[key]
        if not isinstance(entries, list) or len(entries) > 8:
            raise HTTPException(503, 'invalid source summary')
        seen = set()
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != keys:
                raise HTTPException(503, 'invalid summary keys')
            label = entry[value_name]
            if not isinstance(label, str) or label not in accepted or label in seen or not _count(entry['count']):
                raise HTTPException(503, 'invalid summary value')
            seen.add(label)
        if sum(item['count'] for item in entries) != total:
            raise HTTPException(503, 'inconsistent source summary')
    valid_entries('byPlan', _PLAN_KEYS, {'A','B','C','SELF_PAY','OTHER'}, 'plan')
    valid_entries('byKind', _KIND_KEYS, {'checkup','self_pay_only'}, 'kind')
    slots = payload['slotCounts']
    if not isinstance(slots, list) or len(slots) > 1000:
        raise HTTPException(503, 'invalid slot summary')
    last = ''
    sum_slots = 0
    for item in slots:
        if not isinstance(item,dict) or set(item) != _SLOT_KEYS:
            raise HTTPException(503, 'invalid slot record')
        d, t = item['date'], item['time']
        if (not isinstance(d,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',d)
                or not isinstance(t,str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',t)
                or d + t <= last or not _count(item['bookedCount'])
                or item['capacity'] is not None or item['availabilityConfirmed'] is not False):
            raise HTTPException(503, 'invalid slot security state')
        from datetime import date
        try: date.fromisoformat(d)
        except ValueError: raise HTTPException(503, 'invalid slot date') from None
        last = d+t
        sum_slots += item['bookedCount']
    if sum_slots > total:
        raise HTTPException(503, 'invalid slot counts')
    # We return only a new object with a fixed allowlist.
    return {key: payload[key] for key in _TOP}


def read_synthetic_summary() -> dict:
    secret = _secret()
    stamp = str(int(time.time()))
    nonce = secrets.token_urlsafe(28)
    message = f'GET\n{PATH}\n{stamp}\n{nonce}'.encode('ascii')
    signature = hmac.new(secret, message, hashlib.sha256).hexdigest()
    req = Request(ENDPOINT, method='GET', headers={
        'Accept':'application/json', 'X-DOUBTS-Timestamp':stamp,
        'X-DOUBTS-Nonce':nonce, 'X-DOUBTS-Signature':signature,
    })
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(req, timeout=3) as result:
            if result.status != 200:
                raise ValueError('status')
            content = result.read(32_769)
            if len(content) > 32_768:
                raise ValueError('body too large')
            value = json.loads(content.decode('utf-8'))
        return _validate(value)
    except (HTTPError, URLError, OSError, ValueError, UnicodeError, TimeoutError) as exc:
        raise HTTPException(503, 'synthetic Shanlin source unavailable; production was not accessed') from None


def integration_contract() -> dict:
    return {
        'version': 'v3.6.2', 'tenant': 'shanlin',
        'source': 'fixed_localhost_synthetic_signed_summary',
        'readEndpoint': PATH, 'requires': ['existing_shanlin_verified_session',
                                           'dedicated_signed_read_only_service'],
        'containsPatientIdentity': False, 'bookingWritesEnabled': False,
        'productionReadEnabled': False, 'individualStaffRolesVerified': False,
        'note': 'Existing Shanlin credentials are currently admin-level, not individual nurse RBAC.',
    }
