"""Tenant-scoped, session-reusing read-only v3.6.2 gateway (local synthetic)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
import pilot_backend as backend
from platform_console import local_only, platform_read, NO_CACHE
from platform_shanlin_booking_source_v362 import integration_contract, read_synthetic_summary

router = APIRouter()
HEADERS = dict(NO_CACHE)
HEADERS['Pragma'] = 'no-cache'


@router.get('/api/pilot/platform/booking/v362/contract', include_in_schema=False)
def contract(request: Request, sess=Depends(platform_read)):
    local_only(request)
    return JSONResponse(integration_contract(), headers=HEADERS)


@router.get('/api/pilot/platform/booking/v362/synthetic-summary', include_in_schema=False)
def engineer_summary(request: Request, sess=Depends(platform_read)):
    local_only(request)
    return JSONResponse(read_synthetic_summary(), headers=HEADERS)


@router.get('/api/pilot/admin/shanlin/booking/v362/summary', include_in_schema=False)
def clinic_summary(request: Request, sess=Depends(backend.require_clinic)):
    local_only(request)
    if sess.get('clinic') != 'shanlin' or sess.get('role') != 'clinic_admin':
        raise HTTPException(403, 'Shanlin clinic admin session required')
    # Existing Shanlin backend is currently single shared admin credential.
    # Only session validated against original Shanlin clinic ownership qualifies.
    config = sess.get('legacyConfig')
    if not isinstance(config, dict) or config.get('name') != '山林診所':
        raise HTTPException(409, 'Shanlin clinic source ownership not verified')
    return JSONResponse(read_synthetic_summary(), headers=HEADERS)
