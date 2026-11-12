"""DOUBTS v3.2.1: platform-wide standard plan modules; no per-clinic toggles."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

import pilot_backend as backend
import platform_module_store_v32 as legacy_registry
import platform_standard_policy_v321 as standard
import platform_onboarding_store_v3 as onboarding
from platform_console import STATIC, NO_CACHE, local_only, platform_read, platform_write
from platform_module_routes_v32 import (ModuleCreate, ModuleEdit, ModuleArchive,
                                         CSP, API)

router = APIRouter()
REV = r'^[a-f0-9]{32}$'


def _json(value):
    return JSONResponse(value, headers=NO_CACHE)


def _fail(error):
    if isinstance(error, (standard.RevisionConflict, legacy_registry.RevisionConflict)):
        raise HTTPException(409, str(error)) from error
    if isinstance(error, legacy_registry.MissingModule):
        raise HTTPException(404, str(error)) from error
    if isinstance(error, ValueError):
        raise HTTPException(400, str(error)) from error
    raise error


@router.get('/platform/admin', include_in_schema=False)
def admin_page_v321(request: Request):
    local_only(request)
    return FileResponse(STATIC / 'admin-v321.html', media_type='text/html',
                        headers={**NO_CACHE, 'Content-Security-Policy': CSP})


@router.get('/platform/modules', include_in_schema=False)
def module_center_v321(request: Request):
    local_only(request)
    return FileResponse(STATIC / 'module-center-v321.html', media_type='text/html',
                        headers={**NO_CACHE, 'Content-Security-Policy': CSP})


@router.get('/platform/assets/platform-v321.js', include_in_schema=False)
def admin_js_v321(request: Request):
    local_only(request)
    return FileResponse(STATIC / 'platform-v321.js', media_type='application/javascript', headers=NO_CACHE)


@router.get('/platform/assets/module-center-v321.js', include_in_schema=False)
def modules_js_v321(request: Request):
    local_only(request)
    return FileResponse(STATIC / 'module-center-v321.js', media_type='application/javascript', headers=NO_CACHE)


@router.get('/platform/assets/module-center-v321.css', include_in_schema=False)
def modules_css_v321(request: Request):
    local_only(request)
    return FileResponse(STATIC / 'module-center-v321.css', media_type='text/css', headers=NO_CACHE)


@router.get('/platform/clinics/{clinic_id}/setup', include_in_schema=False)
def setup_v321(clinic_id: str, request: Request):
    local_only(request)
    try:
        onboarding._draft(clinic_id)
    except ValueError as error:
        raise HTTPException(404, str(error)) from error
    page = (STATIC / 'clinic-onboarding-v3.html').read_text(encoding='utf-8')
    src = '/platform/assets/clinic-onboarding-v3.js'
    if page.count(src) != 1:
        raise HTTPException(503, '診所設定頁格式不相容，拒絕更新')
    page = page.replace(src, '/platform/assets/clinic-onboarding-v321.js', 1)
    page = page.replace('功能模組預先授權</h2>', '共用標準版功能（平台統一管理）</h2>', 1)
    return HTMLResponse(page, headers={**NO_CACHE, 'Content-Security-Policy': CSP})


@router.get('/platform/assets/clinic-onboarding-v321.js', include_in_schema=False)
def setup_js_v321(request: Request):
    local_only(request)
    return FileResponse(STATIC / 'clinic-onboarding-v321.js', media_type='application/javascript', headers=NO_CACHE)


@router.get(API, include_in_schema=False)
def read_modules(sess=Depends(platform_read)):
    return _json(standard.read_state())


@router.get(API + '/audit', include_in_schema=False)
def audit_modules(sess=Depends(platform_read)):
    return _json({'entries': standard.audit_tail(60)})


@router.get(API + '/migration', include_in_schema=False)
def inspect_old_mapping(sess=Depends(platform_read)):
    return _json(standard.legacy_diagnostics())


@router.post(API, include_in_schema=False)
def create_module(body: ModuleCreate, sess=Depends(platform_write)):
    try:
        legacy_registry.create_module(module_id=body.id, name=body.name,
            description=body.description, planned_version=body.plannedVersion,
            stage=body.stage, expected_revision=body.expectedRevision,
            actor=sess['username'])
        return _json({'success': True, 'registry': standard.read_state()})
    except (legacy_registry.RevisionConflict, legacy_registry.MissingModule, ValueError) as error:
        _fail(error)


@router.patch(API + '/{module_id}', include_in_schema=False)
def edit_module(module_id: str, body: ModuleEdit, sess=Depends(platform_write)):
    try:
        legacy_registry.update_module(module_id=module_id, name=body.name,
            description=body.description, planned_version=body.plannedVersion,
            stage=body.stage, expected_revision=body.expectedRevision,
            actor=sess['username'])
        return _json({'success': True, 'registry': standard.read_state()})
    except (legacy_registry.RevisionConflict, legacy_registry.MissingModule, ValueError) as error:
        _fail(error)


@router.post(API + '/{module_id}/lifecycle', include_in_schema=False)
def archive_module(module_id: str, body: ModuleArchive, sess=Depends(platform_write)):
    try:
        legacy_registry.set_archived(module_id=module_id, archived=body.archived,
            expected_revision=body.expectedRevision, actor=sess['username'])
        return _json({'success': True, 'registry': standard.read_state()})
    except (legacy_registry.RevisionConflict, legacy_registry.MissingModule, ValueError) as error:
        _fail(error)


class StandardPlanToggle(BaseModel):
    enabled: bool
    expectedPolicyRevision: str = Field(pattern=REV)


@router.post(API + '/{module_id}/standard', include_in_schema=False)
def set_global_standard(module_id: str, body: StandardPlanToggle,
                        sess=Depends(platform_write)):
    try:
        state = standard.set_standard(module_id=module_id, enabled=body.enabled,
            expected_revision=body.expectedPolicyRevision, actor=sess['username'])
        return _json({'success': True, 'registry': state})
    except (standard.RevisionConflict, legacy_registry.MissingModule, ValueError) as error:
        _fail(error)


@router.post(API + '/{module_id}/grants', include_in_schema=False)
def per_clinic_grant_retired(module_id: str, sess=Depends(platform_write)):
    raise HTTPException(410, '已改用全平台標準版：不再提供逐診所模組勾選')


@router.post('/api/pilot/platform/console/features', include_in_schema=False)
def v1_grant_retired(sess=Depends(platform_write)):
    raise HTTPException(410, '舊式逐診所功能設定已停用，請使用全平台標準版管理')


@router.post('/api/pilot/platform/console/onboarding/{clinic_id}/features', include_in_schema=False)
def draft_grant_retired(clinic_id: str, sess=Depends(platform_write)):
    raise HTTPException(410, '新診所自動繼承標準版功能清單，不需要逐診所勾選')


@router.get('/api/pilot/admin/platform-features', include_in_schema=False)
def clinic_entitlements(sess=Depends(backend.require_clinic)):
    try:
        return _json(standard.clinic_entitlements(sess['clinic']))
    except ValueError as error:
        raise HTTPException(403, '未授權診所不可使用功能') from error
