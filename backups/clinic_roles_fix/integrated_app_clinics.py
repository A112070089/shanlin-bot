"""Phase 7 local-only clinic-aware navigation and booking-write protection.

Start from website/: python -m uvicorn integrated_app_clinics:app
Preserves Phase 1-6 integrated voice, self-pay previews and pilot admin.
The legacy booking data model has NO clinicId; all real booking writes must
remain disabled until two isolated providers and server-side checks exist.
"""
from fastapi import Request
from fastapi.responses import JSONResponse

from integrated_app_voice import app
from integrated_clinic_routes import router as clinic_router

# Add explicit clinic routes before older generic routes and the original
# /api/clinic-config, /api/availability and /api/questions Firebase readers.
before = len(app.router.routes)
app.include_router(clinic_router)
new_routes = app.router.routes[before:]
del app.router.routes[before:]
app.router.routes[0:0] = new_routes
app.openapi_schema = None


@app.middleware('http')
async def isolated_clinic_preview_guard(request: Request, call_next):
    path = request.url.path
    clinic = request.query_params.get('clinic')
    # The original main.py writes to one non-tenant-qualified appointments path.
    # Never allow a sample form (Yidian OR Shanlin) to write there.
    if path == '/api/booking/confirm' and request.method.upper() != 'OPTIONS':
        return JSONResponse({'detail': '8006 雙診所本機展示不接受正式預約；請先完成診所獨立資料庫與後端核對。'},
                            status_code=423, headers={'Cache-Control': 'no-store'})
    legacy_patient_paths = (
        '/api/self_pay', '/api/booking', '/api/availability',
        '/api/clinic-config', '/api/questions', '/api/integrated/catalog',
    )
    if clinic is not None and clinic != 'yidian' and any(
        path == prefix or path.startswith(prefix + '/') for prefix in legacy_patient_paths
    ):
        return JSONResponse({'detail': '此 API 尚未提供指定診所的獨立資料；避免資料混用。'},
                            status_code=423, headers={'Cache-Control': 'no-store'})
    return await call_next(request)
