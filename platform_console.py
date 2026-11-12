"""Independent engineering console UI/API, reusing the EXISTING pilot platform admin.

Not a second password database. Never changes the clinic-specific session, patient
booking endpoints, voice routes, catalogs, Firebase, or clinic login experience.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import Literal

import pilot_backend as backend
import platform_console_store as db

router = APIRouter()
STATIC = Path(__file__).resolve().parent / 'platform_static'
LAUNCHED = time.monotonic()
LOCAL_CLIENTS = frozenset({'127.0.0.1', '::1', 'localhost', 'testclient'}) | frozenset(('192.168.1.106', '192.168.1.111'))
NO_CACHE = {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
            'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY'}


def local_only(request: Request):
    if request.client is None or request.client.host not in LOCAL_CLIENTS:
        raise HTTPException(403, '此工程師總控台僅允許本機存取')
    # Host header cannot grant access. Deny unexpected hosts as an additional
    # DNS-rebinding guard; do not use forwarded-for or client-controlled headers.
    host = request.url.hostname
    if host not in LOCAL_CLIENTS and host != 'testserver':
        raise HTTPException(403, '此工程師總控台僅允許本機主機名稱')


def platform_read(request: Request, sess=Depends(backend.require_platform)) -> dict:
    local_only(request)
    return sess


def platform_write(request: Request, sess=Depends(backend.require_platform_mutation)) -> dict:
    local_only(request)
    # Always require an Origin for browser mutations, not only CSRF token.
    origin = request.headers.get('origin', '')
    if not origin or origin.rstrip('/') != str(request.base_url).rstrip('/'):
        raise HTTPException(403, '工程師操作必須由同一個網站送出')
    return sess


@router.get('/platform/admin', include_in_schema=False)
def admin_page(request: Request):
    local_only(request)
    return FileResponse(
        STATIC / 'admin.html', media_type='text/html', headers={**NO_CACHE,
            'Content-Security-Policy': "default-src 'none'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"}
    )


@router.get('/platform/assets/platform.css', include_in_schema=False)
def admin_css(request: Request):
    local_only(request)
    return FileResponse(STATIC / 'platform.css', media_type='text/css', headers=NO_CACHE)


@router.get('/platform/assets/platform.js', include_in_schema=False)
def admin_js(request: Request):
    local_only(request)
    return FileResponse(STATIC / 'platform.js', media_type='application/javascript', headers=NO_CACHE)


@router.get('/platform/api/bootstrap', include_in_schema=False)
def bootstrap(request: Request):
    local_only(request)
    return JSONResponse({'accountConfigured': backend.platform_account_exists()}, headers=NO_CACHE)


@router.get('/api/pilot/platform/console/session', include_in_schema=False)
def console_session(sess=Depends(platform_read)):
    return JSONResponse({'username': sess.get('username', ''), 'csrf': sess['csrf'],
                         'expiresAt': sess['expires'], 'role': 'platform_admin'}, headers=NO_CACHE)


@router.get('/api/pilot/platform/console/state', include_in_schema=False)
def console_state(sess=Depends(platform_read)):
    clinics = []
    for clinic, name in db.CLINICS.items():
        # Storage mode describes the *pilot module only*. Do not mistake this
        # for the existence of the original website's Firebase project.
        mode = backend.clinic_storage_mode(clinic)
        clinics.append({
            'id': clinic, 'name': name,
            'role': '公版 Demo' if clinic == 'yidian' else '合作診所',
            'pilotStorageMode': mode,
            'bookingReady': False,
            'adminUrl': f'/pilot?clinic={clinic}&view=admin',
        })
    state = db.read_state()
    return JSONResponse({'clinics': clinics, 'policy': state,
                         'notice': '工程師總控台的預先授權開關尚未接到醫護功能；正式預約仍停用。'},
                        headers=NO_CACHE)


class FeatureMutation(BaseModel):
    clinicId: Literal['shanlin', 'yidian']
    featureId: Literal['ai_health_summary', 'staff_worklist', 'appointment_reminders']
    enabled: bool
    expectedRevision: str = Field(pattern=r'^[a-f0-9]{32}$')


@router.post('/api/pilot/platform/console/features', include_in_schema=False)
def set_feature(body: FeatureMutation, sess=Depends(platform_write)):
    try:
        data = db.update_flag(clinic=body.clinicId, feature=body.featureId,
                              enabled=body.enabled, expected_revision=body.expectedRevision,
                              actor=sess.get('username', 'platform_admin'))
    except db.RevisionConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return JSONResponse({'success': True, 'policy': data}, headers=NO_CACHE)


@router.get('/api/pilot/platform/console/audit', include_in_schema=False)
def console_audit(sess=Depends(platform_read)):
    return JSONResponse({'entries': db.audit_tail(40)}, headers=NO_CACHE)


# Fixed URLs only, not user-controlled or env-controlled: prevent SSRF.
MODEL_SERVICES = (
    ('8002', '台語朗讀模型 TTS', 'http://127.0.0.1:8002/health'),
    ('8003', '台語辨識模型 STT', 'http://127.0.0.1:8003/health'),
    ('8004', '中文轉台語翻譯', 'http://127.0.0.1:8004/health'),
)


def _probe(port: str, title: str, url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=1.6) as response:
            obj = json.loads(response.read(16384).decode('utf-8'))
            ok = (response.status == 200 and isinstance(obj, dict)
                  and (obj.get('status') == 'ok' or obj.get('ready') is True))
            return {'port': port, 'name': title, 'state': 'ready' if ok else 'not_ready'}
    except (OSError, ValueError, UnicodeError, urllib.error.HTTPError):
        return {'port': port, 'name': title, 'state': 'offline'}


@router.get('/api/pilot/platform/console/health', include_in_schema=False)
def console_health(sess=Depends(platform_read)):
    result = [{'port': '8006', 'name': '整合網站', 'state': 'ready'}]
    for port, title, url in MODEL_SERVICES:
        result.append(_probe(port, title, url))
    return JSONResponse({'services': result, 'uptimeSeconds': int(time.monotonic() - LAUNCHED),
                         'testOnly': True}, headers=NO_CACHE)


@router.get('/api/pilot/admin/platform-features', include_in_schema=False)
def clinic_features(sess=Depends(backend.require_clinic)):
    # Binds data to VERIFIED clinic session; ignores query string clinic=.
    return JSONResponse(db.clinic_entitlements(sess['clinic']), headers=NO_CACHE)
