"""v3.6.3 routes: reuse engineer and verified Shanlin clinic session; no mutations."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
import pilot_backend as backend
from platform_console import platform_read, local_only, NO_CACHE
from platform_shanlin_booking_source_v363 import contract, read_test_backend_summary

router = APIRouter()
HEADERS = {**NO_CACHE, 'Pragma': 'no-cache'}


@router.get('/api/pilot/platform/booking/v363/contract', include_in_schema=False)
def status(request: Request, sess=Depends(platform_read)):
    local_only(request)
    return JSONResponse(contract(), headers=HEADERS)


@router.get('/api/pilot/platform/booking/v363/test-summary', include_in_schema=False)
def engineer(request: Request, sess=Depends(platform_read)):
    local_only(request)
    return JSONResponse(read_test_backend_summary(), headers=HEADERS)


@router.get('/api/pilot/admin/shanlin/booking/v363/test-summary', include_in_schema=False)
def shanlin(request: Request, sess=Depends(backend.require_clinic)):
    local_only(request)
    if sess.get('clinic') != 'shanlin' or sess.get('role') != 'clinic_admin':
        raise HTTPException(403, 'verified Shanlin admin session required')
    legacy = sess.get('legacyConfig')
    if not isinstance(legacy,dict) or legacy.get('name') != '山林診所':
        raise HTTPException(409, 'Shanlin ownership not verified')
    return JSONResponse(read_test_backend_summary(), headers=HEADERS)
