"""Additive engineer-only clinic-onboarding draft routes (no production writes)."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from platform_console import STATIC, NO_CACHE, local_only, platform_read, platform_write
import platform_clinic_registry as registry

router = APIRouter()
CSP = "default-src 'none'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"


@router.get('/platform/admin', include_in_schema=False)
def engineer_dashboard_v2(request: Request):
    """Add a non-invasive link without altering the original v1 dashboard file."""
    local_only(request)
    template = (STATIC / 'admin.html').read_text(encoding='utf-8')
    anchor = '<h1>平台總覽</h1>'
    if template.count(anchor) != 1:
        raise HTTPException(503, '現有工程師介面與預期不同，已停止套用新版導覽')
    template = template.replace(
        anchor, '<nav class="center-nav"><a href="/platform/clinics">診所管理中心 →</a></nav>' + anchor, 1)
    template = template.replace('</head>', '<link rel="stylesheet" href="/platform/assets/clinic-center.css"></head>', 1)
    return HTMLResponse(template, headers={**NO_CACHE, 'Content-Security-Policy': CSP})


@router.get('/platform/clinics', include_in_schema=False)
def clinic_center_page(request: Request):
    local_only(request)
    return FileResponse(STATIC / 'clinic-center.html', media_type='text/html',
                        headers={**NO_CACHE, 'Content-Security-Policy': CSP})


@router.get('/platform/assets/clinic-center.js', include_in_schema=False)
def center_js(request: Request):
    local_only(request)
    return FileResponse(STATIC / 'clinic-center.js', media_type='application/javascript', headers=NO_CACHE)


@router.get('/platform/assets/clinic-center.css', include_in_schema=False)
def center_css(request: Request):
    local_only(request)
    return FileResponse(STATIC / 'clinic-center.css', media_type='text/css', headers=NO_CACHE)


@router.get('/api/pilot/platform/console/clinic-registry', include_in_schema=False)
def get_registry(sess=Depends(platform_read)):
    return JSONResponse(registry.read_state(), headers=NO_CACHE)


@router.get('/api/pilot/platform/console/clinic-registry/audit', include_in_schema=False)
def registry_audit(sess=Depends(platform_read)):
    return JSONResponse({'entries': registry.audit_tail()}, headers=NO_CACHE)


class CreateDraft(BaseModel):
    clinicId: str = Field(min_length=3, max_length=32, pattern=r'^[a-z][a-z0-9-]{2,31}$')
    displayName: str = Field(min_length=2, max_length=80)
    notes: str = Field(default='', max_length=240)
    expectedRevision: str = Field(pattern=r'^[a-f0-9]{32}$')


class UpdateDraft(BaseModel):
    displayName: str = Field(min_length=2, max_length=80)
    notes: str = Field(default='', max_length=240)
    archived: bool
    expectedRevision: str = Field(pattern=r'^[a-f0-9]{32}$')


@router.post('/api/pilot/platform/console/clinic-registry/drafts', include_in_schema=False)
def post_draft(body: CreateDraft, sess=Depends(platform_write)):
    try:
        data = registry.create_draft(clinic_id=body.clinicId, display_name=body.displayName,
                                     notes=body.notes, expected_revision=body.expectedRevision,
                                     actor=sess.get('username', 'platform_admin'))
    except registry.RevisionConflict as error:
        raise HTTPException(409, str(error)) from error
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    return JSONResponse({'success': True, 'registry': data}, headers=NO_CACHE)


@router.patch('/api/pilot/platform/console/clinic-registry/drafts/{clinic_id}', include_in_schema=False)
def patch_draft(clinic_id: str, body: UpdateDraft, sess=Depends(platform_write)):
    try:
        data = registry.update_draft(clinic_id=clinic_id, display_name=body.displayName,
                                     notes=body.notes, archived=body.archived,
                                     expected_revision=body.expectedRevision,
                                     actor=sess.get('username', 'platform_admin'))
    except registry.RevisionConflict as error:
        raise HTTPException(409, str(error)) from error
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    return JSONResponse({'success': True, 'registry': data}, headers=NO_CACHE)
