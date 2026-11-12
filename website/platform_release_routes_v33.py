"""v3.3 engineer-only release tracking API. No external deploy actions."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import Literal

import platform_release_store_v33 as store
import pilot_backend as backend
from platform_console import STATIC, NO_CACHE, local_only, platform_read, platform_write
from platform_module_routes_v32 import CSP

router = APIRouter()
API = '/api/pilot/platform/console/releases'
REV = r'^[a-f0-9]{32}$'
MID = r'^[a-z][a-z0-9_]{2,39}$'
CODE = r'^$|^[0-9a-f]{7,64}$'


def _reply(data):
    return JSONResponse(data, headers=NO_CACHE)


def _errors(e):
    if isinstance(e, store.RevisionConflict):
        raise HTTPException(409, str(e)) from e
    if isinstance(e, store.MissingModule):
        raise HTTPException(404, str(e)) from e
    if isinstance(e, RuntimeError):
        raise HTTPException(503, '驗收資料暫時無法讀取；請先檢查資料檔與備份') from e
    if isinstance(e, ValueError):
        raise HTTPException(400, str(e)) from e
    raise e


@router.get('/platform/modules', include_in_schema=False)
def module_center_v33(request: Request):
    local_only(request)
    return FileResponse(STATIC / 'module-center-v33.html', media_type='text/html',
                        headers={**NO_CACHE, 'Content-Security-Policy': CSP})


@router.get('/platform/modules/{module_id}/release', include_in_schema=False)
def release_page(request: Request, module_id: str):
    local_only(request)
    try:
        store._module(module_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return FileResponse(STATIC / 'module-release-v33.html', media_type='text/html',
                        headers={**NO_CACHE, 'Content-Security-Policy': CSP})


@router.get('/platform/assets/module-center-v33.js', include_in_schema=False)
def module_js(request: Request):
    local_only(request)
    return FileResponse(STATIC / 'module-center-v33.js', media_type='application/javascript',
                        headers=NO_CACHE)


@router.get('/platform/assets/module-center-v33.css', include_in_schema=False)
def module_css(request: Request):
    local_only(request)
    return FileResponse(STATIC / 'module-center-v33.css', media_type='text/css',
                        headers=NO_CACHE)


@router.get('/platform/assets/module-release-v33.js', include_in_schema=False)
def release_js(request: Request):
    local_only(request)
    return FileResponse(STATIC / 'module-release-v33.js', media_type='application/javascript',
                        headers=NO_CACHE)


@router.get('/platform/assets/module-release-v33.css', include_in_schema=False)
def release_css(request: Request):
    local_only(request)
    return FileResponse(STATIC / 'module-release-v33.css', media_type='text/css',
                        headers=NO_CACHE)


@router.get(API, include_in_schema=False)
def release_overview(sess=Depends(platform_read)):
    try:
        return _reply(store.list_releases())
    except RuntimeError as e:
        _errors(e)


@router.get(API + '/{module_id}', include_in_schema=False)
def release_details(module_id: str, sess=Depends(platform_read)):
    try:
        return _reply(store.read_release(module_id))
    except (ValueError, RuntimeError) as e:
        _errors(e)


@router.get(API + '/{module_id}/audit', include_in_schema=False)
def release_audit(module_id: str, sess=Depends(platform_read)):
    try:
        return _reply({'entries': store.audit_tail(module_id)})
    except (ValueError, RuntimeError) as e:
        _errors(e)


class ProgressUpdate(BaseModel):
    progress: Literal['planned','developing','testing']
    codeReference: str = Field(default='', pattern=CODE, max_length=64)
    expectedRevision: str = Field(pattern=REV)


class CheckUpdate(BaseModel):
    status: Literal['pending','passed','failed']
    evidence: str = Field(default='', max_length=240)
    expectedRevision: str = Field(pattern=REV)


class Transition(BaseModel):
    expectedRevision: str = Field(pattern=REV)


class Reject(Transition):
    reason: str = Field(min_length=5, max_length=240)


@router.post(API + '/{module_id}/progress', include_in_schema=False)
def update_progress(module_id: str, body: ProgressUpdate, sess=Depends(platform_write)):
    try:
        return _reply(store.set_progress(mid=module_id, progress=body.progress,
            code_reference=body.codeReference, expected_revision=body.expectedRevision,
            actor=sess['username']))
    except (ValueError, RuntimeError, store.RevisionConflict) as e:
        _errors(e)


@router.post(API + '/{module_id}/checks/{check_id}', include_in_schema=False)
def update_check(module_id: str, check_id: str, body: CheckUpdate,
                 sess=Depends(platform_write)):
    try:
        return _reply(store.set_check(mid=module_id, check_id=check_id,
            status=body.status, evidence=body.evidence,
            expected_revision=body.expectedRevision, actor=sess['username']))
    except (ValueError, RuntimeError, store.RevisionConflict) as e:
        _errors(e)


@router.post(API + '/{module_id}/submit', include_in_schema=False)
def submit(module_id: str, body: Transition, sess=Depends(platform_write)):
    try:
        return _reply(store.submit_review(mid=module_id, expected_revision=body.expectedRevision,
                                          actor=sess['username']))
    except (ValueError, RuntimeError, store.RevisionConflict) as e:
        _errors(e)


@router.post(API + '/{module_id}/withdraw', include_in_schema=False)
def withdraw(module_id: str, body: Transition, sess=Depends(platform_write)):
    try:
        return _reply(store.withdraw_review(mid=module_id, expected_revision=body.expectedRevision,
                                            actor=sess['username']))
    except (ValueError, RuntimeError, store.RevisionConflict) as e:
        _errors(e)


@router.post(API + '/{module_id}/approve', include_in_schema=False)
def approve(module_id: str, body: Transition, sess=Depends(platform_write)):
    try:
        return _reply(store.approve_review(mid=module_id, expected_revision=body.expectedRevision,
                                           actor=sess['username']))
    except (ValueError, RuntimeError, store.RevisionConflict) as e:
        _errors(e)


@router.post(API + '/{module_id}/reject', include_in_schema=False)
def reject(module_id: str, body: Reject, sess=Depends(platform_write)):
    try:
        return _reply(store.reject_review(mid=module_id, reason=body.reason,
                 expected_revision=body.expectedRevision, actor=sess['username']))
    except (ValueError, RuntimeError, store.RevisionConflict) as e:
        _errors(e)


@router.get('/api/pilot/admin/platform-features', include_in_schema=False)
def clinic_features_with_acceptance(sess=Depends(backend.require_clinic)):
    try:
        return _reply(store.clinic_entitlements(sess['clinic']))
    except ValueError as e:
        raise HTTPException(403, '診所未獲授權使用此功能') from e
    except RuntimeError as e:
        raise HTTPException(503, '驗收紀錄暫時無法驗證，所有新模組須維持停用') from e
