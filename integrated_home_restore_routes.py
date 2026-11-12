"""Original-homepage-first navigation; catalog is in its original self-pay tool.

This is a localhost-only preview. Patient booking submission is not allowed until
Shanlin's appointment storage is explicitly tenant-isolated and reviewed.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from integrated_clinic_routes import local_only, valid_clinic, preview_config
from integrated_home_restore import (
    HEADERS, build_shanlin_home, build_yidian_home, scoped_booking_preview,
)

router = APIRouter()


@router.get('/', include_in_schema=False)
@router.get('/index.html', include_in_schema=False)
def home(request: Request, clinic: str | None = None):
    local_only(request)
    slug = valid_clinic(clinic)
    return build_shanlin_home() if slug == 'shanlin' else build_yidian_home()


@router.get('/appointment.html', include_in_schema=False)
@router.get('/appointment2.html', include_in_schema=False)
@router.get('/search.html', include_in_schema=False)
@router.get('/booking_success.html', include_in_schema=False)
def booking_entry(request: Request, clinic: str | None = None):
    local_only(request)
    slug = valid_clinic(clinic)
    if slug == 'yidian':
        return RedirectResponse('/?clinic=yidian#scrollspyAppointment', status_code=303, headers=HEADERS)
    return scoped_booking_preview(request.url.path.lstrip('/'), slug)


@router.get('/api/clinic-config', include_in_schema=False)
def clinic_config(request: Request, clinic: str | None = None):
    local_only(request)
    if clinic is None:
        raise HTTPException(423, '請由指定診所首頁進入')
    slug = valid_clinic(clinic)
    if slug == 'yidian':
        return JSONResponse({'status':'success','clinicId':'yidian','previewOnly':True,
                             'clinic':preview_config()}, headers=HEADERS)
    # Preserve original project contact data, not a placeholder. Never read an
    # ambiguous global Firebase booking_config path in this local preview.
    from main import CLINIC_DEFAULTS
    data = {**CLINIC_DEFAULTS, 'name': '山林診所'}
    return JSONResponse({'status':'success','clinicId':'shanlin','previewOnly':True,
                         'clinic':data}, headers=HEADERS)


@router.get('/api/availability', include_in_schema=False)
def availability(request: Request, clinic: str | None = None):
    local_only(request)
    if clinic is None:
        raise HTTPException(423, '必須指定診所')
    slug = valid_clinic(clinic)
    return JSONResponse({'status':'success','clinicId':slug,'previewOnly':True,
                         'elderly':{}, 'selfPay':{}}, headers=HEADERS)


@router.get('/api/questions', include_in_schema=False)
def questions(request: Request, clinic: str | None = None, mode: str = ''):
    local_only(request)
    if clinic is None:
        raise HTTPException(423, '必須指定診所')
    slug = valid_clinic(clinic)
    return JSONResponse({'status':'success','clinicId':slug,'previewOnly':True,
                         'questions':[]}, headers=HEADERS)
