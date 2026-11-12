"""v3.5 local engineer-only status + reused v3.4 conservative source context."""
from __future__ import annotations
from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, JSONResponse
from platform_console import STATIC, NO_CACHE, local_only, platform_read
from platform_module_routes_v32 import CSP
from platform_line_bridge_v35 import check_status

router=APIRouter()

@router.get('/platform/modules',include_in_schema=False)
def module_center_v35(request:Request):
    local_only(request)
    return FileResponse(STATIC/'module-center-v35.html',media_type='text/html',headers={**NO_CACHE,'Content-Security-Policy':CSP})

@router.get('/platform/modules/appointment_reminders/line-status',include_in_schema=False)
def status_page_v35(request:Request):
    local_only(request)
    return FileResponse(STATIC/'line-status-v35.html',media_type='text/html',headers={**NO_CACHE,'Content-Security-Policy':CSP})

@router.get('/platform/assets/module-center-v35.js',include_in_schema=False)
def center_js_v35(request:Request):
    local_only(request)
    return FileResponse(STATIC/'module-center-v35.js',media_type='application/javascript',headers=NO_CACHE)

@router.get('/platform/assets/line-status-v35.js',include_in_schema=False)
def status_js_v35(request:Request):
    local_only(request)
    return FileResponse(STATIC/'line-status-v35.js',media_type='application/javascript',headers=NO_CACHE)

@router.get('/api/pilot/platform/console/line-bot/v35/status',include_in_schema=False)
def status_api_v35(sess=Depends(platform_read)):
    return JSONResponse(check_status(),headers=NO_CACHE)
