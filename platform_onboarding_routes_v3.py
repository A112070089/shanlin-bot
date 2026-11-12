"""V3 local clinic onboarding: independently permissioned engineering operations.

This intentionally does NOT register a third clinic with the original pilot
booking/catalog routes. Live release remains impossible in V3.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from platform_console import STATIC, NO_CACHE, local_only, platform_read, platform_write
import pilot_backend as backend
import platform_onboarding_store_v3 as store

router = APIRouter()
CSP = "default-src 'none'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
API = '/api/pilot/platform/console/onboarding'


def _respond(obj):
    return JSONResponse(obj, headers=NO_CACHE)


def _error(exc):
    if isinstance(exc, store.RevisionConflict):
        raise HTTPException(409, str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(400, str(exc)) from exc
    raise exc


@router.get('/platform/clinics/{clinic_id}/setup', include_in_schema=False)
def onboarding_page(clinic_id: str, request: Request):
    local_only(request)
    try:
        store._draft(clinic_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return FileResponse(STATIC / 'clinic-onboarding-v3.html', media_type='text/html',
                        headers={**NO_CACHE, 'Content-Security-Policy': CSP})


@router.get('/platform/assets/clinic-onboarding-v3.js', include_in_schema=False)
def onboarding_js(request: Request):
    local_only(request)
    return FileResponse(STATIC / 'clinic-onboarding-v3.js', media_type='application/javascript', headers=NO_CACHE)


@router.get('/platform/assets/clinic-onboarding-v3.css', include_in_schema=False)
def onboarding_css(request: Request):
    local_only(request)
    return FileResponse(STATIC / 'clinic-onboarding-v3.css', media_type='text/css', headers=NO_CACHE)


@router.get('/platform/clinic-onboarding-login', include_in_schema=False)
def clinic_onboarding_login_page(request: Request):
    local_only(request)
    return FileResponse(STATIC / 'clinic-onboarding-login-v3.html', media_type='text/html',
                        headers={**NO_CACHE, 'Content-Security-Policy': CSP})


@router.get('/platform/assets/clinic-onboarding-login-v3.js', include_in_schema=False)
def clinic_onboarding_login_js(request: Request):
    local_only(request)
    return FileResponse(STATIC / 'clinic-onboarding-login-v3.js', media_type='application/javascript', headers=NO_CACHE)


@router.get(API+'/{clinic_id}', include_in_schema=False)
def read_onboarding(clinic_id: str, sess=Depends(platform_read)):
    try:
        return _respond(store.read(clinic_id))
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get(API+'/{clinic_id}/audit', include_in_schema=False)
def read_onboarding_audit(clinic_id: str, sess=Depends(platform_read)):
    try:
        return _respond({'entries': store.audit_tail(clinic_id)})
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


class Profile(BaseModel):
    phone: str = Field(default='', max_length=30)
    address: str = Field(default='', max_length=160)
    hours: str = Field(default='', max_length=100)
    expectedRevision: str = Field(pattern=r'^[0-9a-f]{32}$')


class Account(BaseModel):
    username: str = Field(min_length=4, max_length=64)
    password: str = Field(min_length=12, max_length=256)
    reset: bool = False
    expectedRevision: str = Field(pattern=r'^[0-9a-f]{32}$')


class Storage(BaseModel):
    mode: str = Field(pattern=r'^(unconfigured|firebase_rtdb)$')
    expectedRevision: str = Field(pattern=r'^[0-9a-f]{32}$')


class Feature(BaseModel):
    featureId: str = Field(min_length=3, max_length=64)
    enabled: bool
    expectedRevision: str = Field(pattern=r'^[0-9a-f]{32}$')


class Review(BaseModel):
    expectedRevision: str = Field(pattern=r'^[0-9a-f]{32}$')


@router.post(API+'/{clinic_id}/profile', include_in_schema=False)
def update_profile(clinic_id: str, body: Profile, sess=Depends(platform_write)):
    try:
        return _respond(store.save_profile(clinic_id, phone=body.phone, address=body.address,
                                            hours=body.hours, revision=body.expectedRevision,
                                            actor=sess['username']))
    except (ValueError, store.RevisionConflict) as exc:
        _error(exc)


@router.post(API+'/{clinic_id}/account', include_in_schema=False)
def create_account(clinic_id: str, body: Account, sess=Depends(platform_write)):
    try:
        return _respond(store.save_account(clinic_id, username=body.username,
                                           password=body.password, reset=body.reset,
                                           revision=body.expectedRevision, actor=sess['username']))
    except (ValueError, store.RevisionConflict) as exc:
        _error(exc)


@router.post(API+'/{clinic_id}/storage', include_in_schema=False)
def update_storage(clinic_id: str, body: Storage, sess=Depends(platform_write)):
    try:
        return _respond(store.save_storage_mode(clinic_id, mode=body.mode,
                                               revision=body.expectedRevision, actor=sess['username']))
    except (ValueError, store.RevisionConflict) as exc:
        _error(exc)


@router.post(API+'/{clinic_id}/features', include_in_schema=False)
def update_feature(clinic_id: str, body: Feature, sess=Depends(platform_write)):
    try:
        return _respond(store.save_feature(clinic_id, feature_id=body.featureId,
                                           enabled=body.enabled, revision=body.expectedRevision,
                                           actor=sess['username']))
    except (ValueError, store.RevisionConflict) as exc:
        _error(exc)


@router.post(API+'/{clinic_id}/review', include_in_schema=False)
def submit_review(clinic_id: str, body: Review, sess=Depends(platform_write)):
    try:
        return _respond(store.submit_review(clinic_id, revision=body.expectedRevision,
                                            actor=sess['username']))
    except (ValueError, store.RevisionConflict) as exc:
        _error(exc)


class StagingLogin(BaseModel):
    clinicId: str = Field(min_length=3, max_length=32)
    username: str = Field(min_length=4, max_length=64)
    password: str = Field(min_length=1, max_length=256)


@router.post('/api/pilot/onboarding/login', include_in_schema=False)
def staging_login(body: StagingLogin, request: Request, response: Response):
    local_only(request)
    # Only same-origin requests; this is a LOCAL TEST, not a production login.
    origin = request.headers.get('origin', '')
    if not origin or origin.rstrip('/') != str(request.base_url).rstrip('/'):
        raise HTTPException(403, '跨站登入要求已拒絕')
    ip = backend.check_login_limit(request)
    if not store.check_account(body.clinicId, username=body.username, password=body.password):
        backend.fail_login(ip)
    token = backend.new_session(body.clinicId, role='onboarding_admin', username=body.username)
    backend.issue_cookie(request, response, token)
    backend.audit('staging_clinic_login', body.username, body.clinicId)
    return {'success': True, 'clinicId': body.clinicId, 'role': 'onboarding_admin',
            'notice': '僅供本機驗證帳密，未授予病患資料或正式預約操作權限'}


@router.get('/api/pilot/onboarding/session', include_in_schema=False)
def staging_session(request: Request, sess=Depends(backend.authorized)):
    local_only(request)
    if sess.get('role') != 'onboarding_admin':
        raise HTTPException(403, '此頁僅供新診所導入帳號驗證')
    slug = sess.get('clinic')
    # A credential rotation or archive invalidates the useful session.
    try:
        draft = store._draft(slug)
    except ValueError as exc:
        raise HTTPException(403, '診所草稿不可使用') from exc
    if draft['archived']:
        raise HTTPException(403, '診所草稿已封存')
    return _respond({'clinicId': slug, 'displayName': draft['displayName'],
                     'username': sess['username'], 'role': 'onboarding_admin',
                     'readyForBooking': False, 'readyForProduction': False})
