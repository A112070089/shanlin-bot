"""DOUBTS v3.6.1 secured clinic-scoped read-only synthetic appointment bridge."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
import pilot_backend as backend
from platform_console import local_only, platform_read, NO_CACHE
from platform_shanlin_booking_source_v361 import read_shanlin_sandbox, source_contract

router = APIRouter()
HEADERS = dict(NO_CACHE)


@router.get('/api/pilot/platform/booking/v361/contract', include_in_schema=False)
def readonly_booking_contract(request: Request, sess=Depends(platform_read)):
    local_only(request)
    return JSONResponse(source_contract(), headers=HEADERS)


@router.get('/api/pilot/platform/booking/v361/sandbox-snapshot', include_in_schema=False)
def engineer_synthetic_booking_snapshot(request: Request, sess=Depends(platform_read)):
    """Engineer can validate MOCK HTTP bridge without Shanlin production login."""
    local_only(request)
    return JSONResponse(read_shanlin_sandbox(), headers=HEADERS)


@router.get('/api/pilot/admin/shanlin/booking/v361/snapshot', include_in_schema=False)
def readonly_shanlin_booking_snapshot(request: Request, sess=Depends(backend.require_clinic)):
    local_only(request)
    # The tenant comes ONLY from the server-validated session, never from a query.
    if sess.get('clinic') != 'shanlin':
        raise HTTPException(403, '此來源僅供已驗證山林診所管理員')
    if not isinstance(sess.get('legacyConfig'), dict) or sess['legacyConfig'].get('name') != '山林診所':
        raise HTTPException(409, '尚未驗證山林診所原後台來源，禁止跨診所讀取')
    return JSONResponse(read_shanlin_sandbox(), headers=HEADERS)
