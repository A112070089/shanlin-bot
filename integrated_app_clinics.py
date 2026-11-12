"""Phase 7 local-only clinic-aware navigation and booking-write protection.

Start from website/: python -m uvicorn integrated_app_clinics:app
Keeps Phase 1-6 implementation isolated; clinic-aware preview blocks
legacy catalog endpoints to avoid presenting Shanlin prices as Yidian.
The legacy booking data model has NO clinicId; all real booking writes must
remain disabled until two isolated providers and server-side checks exist.
"""
from fastapi import Request
from fastapi.responses import JSONResponse

from copy import copy
from integrated_app_voice import app as voice_app

# Clone the local Phase 6 ASGI application before adding clinic-specific routes.
# Previous phases retain their own routes for regression testing; Phase 7+ does
# not silently rewrite the global main.app singleton in the same Python process.
app = copy(voice_app)
# 建立獨立 Router，避免不同 Starlette 版本的內部屬性差異
app.router = type(voice_app.router)(
    routes=list(voice_app.router.routes),
    redirect_slashes=voice_app.router.redirect_slashes,
    on_startup=list(voice_app.router.on_startup),
    on_shutdown=list(voice_app.router.on_shutdown),
    lifespan=voice_app.router.lifespan_context,
    dependency_overrides_provider=voice_app.router.dependency_overrides_provider,
    route_class=voice_app.router.route_class,
)
app.user_middleware = list(voice_app.user_middleware)
app.middleware_stack = None
app.openapi_schema = None
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
    # ALL legacy catalog requests are blocked on this clinic-aware entrypoint,
    # even if they omit clinic=. Yidian has no catalog; Shanlin's source is
    # exposed only through its explicitly Shanlin-scoped read-only route.
    if any(path == prefix or path.startswith(prefix + '/')
           for prefix in ('/api/self_pay', '/api/integrated/catalog')):
        return JSONResponse({'detail': '此診所尚未啟用獨立的預約目錄 API。頤典公版不含項目，山林請使用唯讀來源目錄。'},
                            status_code=423, headers={'Cache-Control': 'no-store'})
    legacy_patient_paths = (
        '/api/booking', '/api/availability',
        '/api/clinic-config', '/api/questions',
    )
    if clinic is not None and clinic != 'yidian' and any(
        path == prefix or path.startswith(prefix + '/') for prefix in legacy_patient_paths
    ):
        return JSONResponse({'detail': '此 API 尚未提供指定診所的獨立資料；避免資料混用。'},
                            status_code=423, headers={'Cache-Control': 'no-store'})
    return await call_next(request)
