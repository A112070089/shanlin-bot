"""Local engineer-only, read-only LINE Bot overview. Does not send messages."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, JSONResponse

from platform_console import STATIC, NO_CACHE, local_only, platform_read
from platform_module_routes_v32 import CSP
import platform_line_bridge_v34 as bridge

router = APIRouter()
API = '/api/pilot/platform/console/line-bot'


def _json(payload):
    return JSONResponse(payload, headers=NO_CACHE)


@router.get('/platform/modules', include_in_schema=False)
def module_center_v34(request: Request):
    local_only(request)
    return FileResponse(STATIC/'module-center-v34.html', media_type='text/html',
                        headers={**NO_CACHE,'Content-Security-Policy':CSP})


@router.get('/platform/modules/appointment_reminders/line-status', include_in_schema=False)
def line_status_page(request: Request):
    local_only(request)
    return FileResponse(STATIC/'line-status-v34.html', media_type='text/html',
                        headers={**NO_CACHE,'Content-Security-Policy':CSP})


@router.get('/platform/assets/module-center-v34.js', include_in_schema=False)
def module_center_script(request: Request):
    local_only(request)
    return FileResponse(STATIC/'module-center-v34.js',media_type='application/javascript', headers=NO_CACHE)


@router.get('/platform/assets/line-status-v34.js', include_in_schema=False)
def line_status_script(request: Request):
    local_only(request)
    return FileResponse(STATIC/'line-status-v34.js',media_type='application/javascript', headers=NO_CACHE)


@router.get('/platform/assets/line-status-v34.css', include_in_schema=False)
def line_status_css(request: Request):
    local_only(request)
    return FileResponse(STATIC/'line-status-v34.css',media_type='text/css', headers=NO_CACHE)


@router.get(API + '/overview', include_in_schema=False)
def line_overview(sess=Depends(platform_read)):
    return _json({'integration':bridge.source_summary(), 'service':{'state':'not_checked', 'label':'尚未執行連線檢查'},
                  'noPatientData':True,'readOnly':True})


@router.get(API + '/probe', include_in_schema=False)
def line_probe(sess=Depends(platform_read)):
    return _json(bridge.probe_status())
