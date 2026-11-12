"""DOUBTS v3.6 read-only clinic operations hub on EXISTING v3.5 sessions.

No booking endpoint, Firebase writes, LINE trigger, or additional user database.
Never import the legacy Shanlin main app in this module.
"""
from __future__ import annotations

from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

import pilot_backend as backend
from platform_console import STATIC, NO_CACHE, local_only, platform_read
from platform_ops_evidence_v36 import all_reports, clinic_report

router = APIRouter()
CSP = ("default-src 'none'; style-src 'self'; script-src 'self'; "
       "connect-src 'self'; img-src 'self'; base-uri 'none'; "
       "frame-ancestors 'none'; form-action 'self'")
SECURE_HEADERS = {**NO_CACHE, 'Content-Security-Policy': CSP}
ORIGINAL_DASHBOARD = STATIC / 'admin-v321.html'


def _catalog_summary() -> tuple[bool, int]:
    # Best-effort local SOURCE file metadata only, not the content of records.
    # An absent source is a pending state. Do not fall back to Yidian catalog.
    try:
        from pilot_shanlin_catalog import snapshot_source_catalog
        value = snapshot_source_catalog(Path(__file__).resolve().parent)
        count = value.get('count', 0) if isinstance(value, dict) else 0
        return bool(value.get('available', False)), count if type(count) is int and count >= 0 else 0
    except (OSError, ValueError, KeyError, RuntimeError, TypeError):
        return False, 0


def _module_count() -> int | None:
    try:
        import platform_standard_policy_v321 as policy
        data = policy.read_state()
        return len(data['modules']) if isinstance(data.get('modules'), list) else 0
    except (OSError, ValueError, KeyError, RuntimeError, TypeError):
        return None


@router.get('/platform/admin', include_in_schema=False)
def dashboard_with_operations_link(request: Request):
    """Reuse original v3.2.1 dashboard JS + CSS, add exactly one navigation link.

    Original on-disk HTML remains unchanged. If anchor changes, fail closed.
    """
    local_only(request)
    try:
        page = ORIGINAL_DASHBOARD.read_text(encoding='utf-8')
    except OSError as exc:
        raise HTTPException(503, '原工程師首頁不可讀，停止公版入口變更') from exc
    anchor = '<a href="/platform/modules">功能模組管理中心 →</a>'
    if page.count(anchor) != 1:
        raise HTTPException(503, '工程師首頁版本與新增入口不相容，未修改原版')
    page = page.replace(anchor, anchor + '\n        <a href="/platform/operations">診所營運整合驗收 →</a>', 1)
    return HTMLResponse(page, headers=SECURE_HEADERS)


@router.get('/platform/operations', include_in_schema=False)
def operations_page(request: Request):
    local_only(request)
    return FileResponse(STATIC / 'clinic-operations-v36.html', media_type='text/html', headers=SECURE_HEADERS)


@router.get('/platform/assets/clinic-operations-v36.js', include_in_schema=False)
def operations_script(request: Request):
    local_only(request)
    return FileResponse(STATIC / 'clinic-operations-v36.js', media_type='application/javascript',
                        headers=NO_CACHE)


@router.get('/api/pilot/platform/operations/v36/summary', include_in_schema=False)
def operations_summary(sess=Depends(platform_read)):
    available, count = _catalog_summary()
    return JSONResponse(all_reports(shanlin_catalog_available=available,
                                    shanlin_catalog_count=count,
                                    module_count=_module_count()), headers=NO_CACHE)


@router.get('/api/pilot/admin/operations/v36/summary', include_in_schema=False)
def own_clinic_summary(request: Request, sess=Depends(backend.require_clinic)):
    local_only(request)
    clinic = sess.get('clinic')
    if clinic not in ('yidian', 'shanlin'):
        raise HTTPException(403, '診所工作階段不正確')
    available, count = _catalog_summary()
    return JSONResponse(clinic_report(
        clinic, authenticated=True,
        shanlin_source_verified=bool(clinic == 'shanlin' and sess.get('legacyConfig')),
        shanlin_catalog_available=available,
        shanlin_catalog_count=count,
        platform_module_count=_module_count(),
    ), headers=NO_CACHE)
