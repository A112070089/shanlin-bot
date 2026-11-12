"""DOUBTS v3.6.1: real local HTTP bridging, NEVER real patient read.

Only a purpose-built synthetic booking sandbox on 127.0.0.1:8017 is allowed.
Do not replace the URL with the production Shanlin Railway API. Live access
requires a separate least-privilege, privacy-reviewed, read-only endpoint.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from hashlib import sha256
from hmac import new as hmac_new
import json
import os
import re
import urllib.error
import urllib.request

from fastapi import HTTPException

SANDBOX_TAG = 'DOUBTS-SANDBOX-V361'
SANDBOX_ORIGIN = 'http://127.0.0.1:8017'
_SANDBOX_ENDPOINTS = ('/api/admin/clinic-config', '/api/admin/appointments')
_ALLOWED_SOURCES = {'LINE', '網站', '電話', '現場', '櫃台', 'Excel', '手動', 'SELF_PAY_BOOKING'}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _sandbox_settings() -> tuple[str, bytes]:
    if os.environ.get('PILOT_V361_SANDBOX_READ_ENABLED') != '1':
        raise HTTPException(423, 'v3.6.1 模擬來源未啟用，正式預約來源仍維持隔離')
    token = os.environ.get('PILOT_V361_SANDBOX_TOKEN', '')
    hash_key = os.environ.get('PILOT_V361_SANDBOX_HASH_KEY', '')
    if (len(token) < 24 or len(hash_key) < 32 or token == hash_key
            or any(x in token for x in '\r\n') or any(x in hash_key for x in '\r\n')):
        raise HTTPException(503, '本機模擬來源的獨立測試金鑰尚未正確設定')
    return token, hash_key.encode('utf-8')


def _get_json(endpoint: str, token: str) -> dict:
    if endpoint not in _SANDBOX_ENDPOINTS:
        raise HTTPException(503, '不允許的測試介接路徑')
    # Fixed loopback origin and HTTP verb. Never forward user URL/path or browser token.
    req = urllib.request.Request(SANDBOX_ORIGIN + endpoint,
                                 method='GET', headers={'X-Sandbox-Token': token,
                                                         'Accept': 'application/json'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(req, timeout=3) as response:
            if response.status != 200:
                raise ValueError('unexpected status')
            content = response.read(300_001)
            if len(content) > 300_000:
                raise ValueError('oversize sandbox reply')
            result = json.loads(content.decode('utf-8'))
            if not isinstance(result, dict):
                raise ValueError('wrong sandbox response shape')
            return result
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
            OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        # No credentials or upstream body in error detail.
        raise HTTPException(503, '山林模擬 API 無法完成安全讀取，未使用正式病患資料') from None


def _valid_date(value: object) -> str | None:
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return None
    try:
        date.fromisoformat(value)
    except ValueError:
        return None
    return value


def _valid_time(value: object) -> str | None:
    return value if isinstance(value, str) and re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value) else None


def _safe_plan(value: object) -> str:
    if not isinstance(value, str):
        return 'other'
    v = value.strip().upper()
    return v if v in ('A', 'B', 'C', 'SELF_PAY') else 'other'


def _safe_source(value: object) -> str:
    return value if isinstance(value, str) and value in _ALLOWED_SOURCES else '其他'


def normalize_synthetic_bookings(payload: dict, *, hash_key: bytes) -> dict:
    """Convert original Shanlin admin listing to a strictly non-PII contract.

    The untrusted response may contain names, phones, Taiwan IDs, diagnoses,
    notes, LINE identities and a raw _key equal to an ID. None is copied out.
    This decoder is used ONLY with the v361 synthetic sandbox.
    """
    if not isinstance(payload, dict) or payload.get('sourceTag') != SANDBOX_TAG:
        raise HTTPException(503, '來源不符合隔離測試規格')
    rows = payload.get('appointments')
    if not isinstance(rows, list) or len(rows) > 1000:
        raise HTTPException(503, '測試預約資料形狀或筆數不符規格')
    if not isinstance(hash_key, bytes) or len(hash_key) < 32:
        raise HTTPException(503, '測試來源鍵值未設定')
    preview = []
    by_day = Counter()
    for row in rows:
        if not isinstance(row, dict):
            raise HTTPException(503, '來源預約記錄格式不正確')
        raw_key = row.get('_key')
        if not isinstance(raw_key, str) or not raw_key or len(raw_key) > 128:
            raise HTTPException(503, '來源預約識別欄位不正確')
        # Never expose raw_key, which could contain phone or national ID.
        ref = hmac_new(hash_key, ('shanlin\0' + raw_key).encode('utf-8'), sha256).hexdigest()[:24]
        if any(x['ref'] == ref for x in preview):
            raise HTTPException(503, '來源預約識別值重複，停止匯入')
        pure_selfpay = row.get('_pureSelfPay') is True
        day = _valid_date(row.get('selfPayDate') if pure_selfpay else row.get('date'))
        slot = _valid_time(row.get('selfPayTime') if pure_selfpay else row.get('time'))
        if day and slot:
            by_day[(day, slot)] += 1
        preview.append({
            'ref': ref,
            'kind': 'self_pay_only' if pure_selfpay else 'checkup',
            'date': day,
            'time': slot,
            'plan': 'SELF_PAY' if pure_selfpay else _safe_plan(row.get('plan')),
            'source': _safe_source(row.get('source')),
            'selfPayIncluded': bool(row.get('_hasSelfPay')),
        })
    return {
        'clinicId': 'shanlin', 'mode': 'sandbox_only',
        'source': 'shanlin_synthetic_http_api', 'sourceVerified': True,
        'isSynthetic': True, 'containsPatientIdentity': False,
        'bookingWritesEnabled': False, 'capacityVerified': False,
        'remindersEnabled': False, 'count': len(preview),
        'appointments': preview,
        'slotCounts': [
            {'date': d, 'time': t, 'bookedCount': count,
             'capacity': None, 'availabilityConfirmed': False}
            for (d,t), count in sorted(by_day.items())
        ],
        'notice': '僅為山林格式之虛構資料介接驗證；名額上限、正式身分與預約交易尚未串接。',
    }


def read_shanlin_sandbox() -> dict:
    token, hash_key = _sandbox_settings()
    config = _get_json('/api/admin/clinic-config', token)
    clinic = config.get('clinic')
    if (config.get('sourceTag') != SANDBOX_TAG
            or config.get('configured') is not True
            or not isinstance(clinic, dict)
            or clinic.get('name') != '山林診所'):
        raise HTTPException(409, '測試來源診所身分不符，禁止跨診所混用')
    payload = _get_json('/api/admin/appointments', token)
    return normalize_synthetic_bookings(payload, hash_key=hash_key)


def source_contract() -> dict:
    """Public-safe contract metadata, not access to patient records."""
    return {
        'schema': 'doubts-clinic-booking-readonly/v361',
        'requires': ['verified_shanlin_clinic_session', 'synthetic_source', 'local_only'],
        'originalAdminPaths': ['/api/admin/clinic-config', '/api/admin/appointments'],
        'identityFieldsExcluded': ['name', 'phone', 'idNumber', 'birth', 'note', 'lineUserId', '_key'],
        'enabledModes': ['disabled', 'sandbox_only'],
        'productionReadEnabled': False,
        'bookingWritesEnabled': False,
        'caveat': '山林原後台使用管理密碼且回傳個資；正式來源必須先新增專用唯讀授權 API。',
    }
