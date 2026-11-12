"""Local-only engineer module catalog and entitlement APIs for DOUBTS v3.2.

This router is inserted before the previous v3.1 router without overwriting it.
New registry is authoritative for v3.2; legacy v1 mutation endpoint returns 410.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

import pilot_backend as backend
import platform_module_store_v32 as store
import platform_onboarding_store_v3 as onboarding
import platform_lifecycle_store_v31 as lifecycle
import platform_clinic_registry as clinics_v2
from platform_console import (STATIC, NO_CACHE, local_only,
                              platform_read, platform_write)

router = APIRouter()
API = '/api/pilot/platform/console/modules'
CSP = "default-src 'none'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
REV = r'^[a-f0-9]{32}$'
MID = r'^[a-z][a-z0-9_]{2,39}$'


def _return(value):
    return JSONResponse(value, headers=NO_CACHE)


def _fail(error):
    if isinstance(error, store.RevisionConflict):
        raise HTTPException(409, str(error)) from error
    if isinstance(error, store.MissingModule):
        raise HTTPException(404, str(error)) from error
    if isinstance(error, ValueError):
        raise HTTPException(400, str(error)) from error
    raise error


@router.get('/platform/admin', include_in_schema=False)
def console_admin_v32(request: Request):
    local_only(request)
    return FileResponse(STATIC / 'admin-v32.html', media_type='text/html',
                        headers={**NO_CACHE, 'Content-Security-Policy': CSP})


@router.get('/platform/assets/platform-v32.js', include_in_schema=False)
def dashboard_js_v32(request: Request):
    local_only(request)
    return FileResponse(STATIC / 'platform-v32.js', media_type='application/javascript', headers=NO_CACHE)


@router.get('/platform/modules', include_in_schema=False)
def module_center_page(request: Request):
    local_only(request)
    return FileResponse(STATIC / 'module-center-v32.html', media_type='text/html',
                        headers={**NO_CACHE, 'Content-Security-Policy': CSP})


@router.get('/platform/assets/module-center-v32.js', include_in_schema=False)
def module_center_js(request: Request):
    local_only(request)
    return FileResponse(STATIC / 'module-center-v32.js', media_type='application/javascript', headers=NO_CACHE)


@router.get('/platform/assets/module-center-v32.css', include_in_schema=False)
def module_center_css(request: Request):
    local_only(request)
    return FileResponse(STATIC / 'module-center-v32.css', media_type='text/css', headers=NO_CACHE)


@router.get('/platform/clinics/{clinic_id}/setup', include_in_schema=False)
def onboarding_page_with_dynamic_modules(clinic_id: str, request: Request):
    local_only(request)
    try:
        onboarding._draft(clinic_id)
    except ValueError as error:
        raise HTTPException(404, str(error)) from error
    page = (STATIC / 'clinic-onboarding-v3.html').read_text(encoding='utf-8')
    old = '/platform/assets/clinic-onboarding-v3.js'
    if page.count(old) != 1:
        raise HTTPException(503, '開通頁版本不相容，拒絕替換模組管理入口')
    page = page.replace(old, '/platform/assets/clinic-onboarding-v32.js', 1)
    page = page.replace('功能模組預先授權</h2>', '功能模組授權管理（v3.2）</h2>', 1)
    return HTMLResponse(page, headers={**NO_CACHE, 'Content-Security-Policy': CSP})


@router.get('/platform/assets/clinic-onboarding-v32.js', include_in_schema=False)
def onboarding_js_v32(request: Request):
    local_only(request)
    return FileResponse(STATIC / 'clinic-onboarding-v32.js', media_type='application/javascript', headers=NO_CACHE)


@router.post('/api/pilot/platform/console/onboarding/{clinic_id}/features', include_in_schema=False)
def retired_v3_draft_feature_mutation(clinic_id: str, sess=Depends(platform_write)):
    raise HTTPException(410, 'v3 開通草稿舊模組授權已移至 v3.2 功能模組管理中心')


class PurgeDraft(BaseModel):
    confirmation: str = Field(min_length=3, max_length=32)
    expectedRegistryRevision: str = Field(pattern=REV)
    expectedOnboardingRevision: str = Field(pattern=REV)


@router.delete('/api/pilot/platform/console/clinic-registry/drafts/{clinic_id}', include_in_schema=False)
def purge_draft_and_v32_grants(clinic_id: str, body: PurgeDraft, sess=Depends(platform_write)):
    # V3.1 is authoritative for guarded deletion. V3.2 only removes orphaned
    # preauthorization metadata AFTER V3.1 has safely completed its purge.
    try:
        result = lifecycle.purge(
            slug=clinic_id, confirmation=body.confirmation,
            registry_revision=body.expectedRegistryRevision,
            onboarding_revision=body.expectedOnboardingRevision,
            actor=sess['username'])
    except clinics_v2.RevisionConflict as error:
        raise HTTPException(409, str(error)) from error
    except lifecycle.DeletionBlocked as error:
        raise HTTPException(409, str(error)) from error
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    try:
        store.remove_deleted_draft_grants(clinic_id=clinic_id, actor=sess['username'])
    except (ValueError, RuntimeError, OSError):
        # V3.1 deletion cannot be rolled back. Orphan flags can NEVER become
        # entitlements because V3.1 permanently tombstones the tenant ID.
        result['notice'] += '；v3.2 授權中繼資料清理未完成，請由工程師檢查。'
    return _return(result)


@router.get(API, include_in_schema=False)
def modules_state(sess=Depends(platform_read)):
    return _return(store.read_state())


@router.get(API + '/audit', include_in_schema=False)
def modules_audit(sess=Depends(platform_read)):
    return _return({'entries': store.audit_tail(60)})


class ModuleCreate(BaseModel):
    id: str = Field(min_length=3, max_length=40, pattern=MID)
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default='', max_length=500)
    plannedVersion: str = Field(min_length=5, max_length=40)
    stage: str = Field(default='planned', pattern=r'^(planned|testing)$')
    expectedRevision: str = Field(pattern=REV)


class ModuleEdit(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default='', max_length=500)
    plannedVersion: str = Field(min_length=5, max_length=40)
    stage: str = Field(pattern=r'^(planned|testing)$')
    expectedRevision: str = Field(pattern=REV)


class ModuleArchive(BaseModel):
    archived: bool
    expectedRevision: str = Field(pattern=REV)


class ModuleGrant(BaseModel):
    clinicId: str = Field(min_length=3, max_length=32, pattern=r'^[a-z][a-z0-9-]{2,31}$')
    enabled: bool
    expectedRevision: str = Field(pattern=REV)


@router.post(API, include_in_schema=False)
def module_create(body: ModuleCreate, sess=Depends(platform_write)):
    try:
        return _return({'success': True, 'registry': store.create_module(
            module_id=body.id, name=body.name, description=body.description,
            planned_version=body.plannedVersion, stage=body.stage,
            expected_revision=body.expectedRevision, actor=sess['username'])})
    except (ValueError, store.RevisionConflict) as error:
        _fail(error)


@router.patch(API + '/{module_id}', include_in_schema=False)
def module_edit(module_id: str, body: ModuleEdit, sess=Depends(platform_write)):
    try:
        return _return({'success': True, 'registry': store.update_module(
            module_id=module_id, name=body.name, description=body.description,
            planned_version=body.plannedVersion, stage=body.stage,
            expected_revision=body.expectedRevision, actor=sess['username'])})
    except (ValueError, store.RevisionConflict) as error:
        _fail(error)


@router.post(API + '/{module_id}/lifecycle', include_in_schema=False)
def module_lifecycle(module_id: str, body: ModuleArchive, sess=Depends(platform_write)):
    try:
        return _return({'success': True, 'registry': store.set_archived(
            module_id=module_id, archived=body.archived,
            expected_revision=body.expectedRevision, actor=sess['username'])})
    except (ValueError, store.RevisionConflict) as error:
        _fail(error)


@router.post(API + '/{module_id}/grants', include_in_schema=False)
def module_grant(module_id: str, body: ModuleGrant, sess=Depends(platform_write)):
    try:
        return _return({'success': True, 'registry': store.set_grant(
            module_id=module_id, clinic_id=body.clinicId, enabled=body.enabled,
            expected_revision=body.expectedRevision, actor=sess['username'])})
    except (ValueError, store.RevisionConflict) as error:
        _fail(error)


@router.post('/api/pilot/platform/console/features', include_in_schema=False)
def legacy_mutation_retired(sess=Depends(platform_write)):
    # Prevent the old v1 hard-coded UI/API from secretly diverging from v3.2.
    raise HTTPException(410, '舊模組授權 API 已停用，請改用工程師功能模組管理中心')


@router.get('/api/pilot/admin/platform-features', include_in_schema=False)
def clinic_features_v32(sess=Depends(backend.require_clinic)):
    # Must use VERIFIED session tenant; caller may not select arbitrary clinic.
    try:
        return _return(store.clinic_entitlements(sess['clinic']))
    except ValueError as error:
        raise HTTPException(403, '此診所不可使用功能模組') from error
