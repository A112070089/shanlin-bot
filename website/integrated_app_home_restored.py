"""Use original site layout for BOTH clinics without sharing appointment writes.

Start on Mac in website/: 
 TAIGI_STT_ENABLED=1 TAIGI_TTS_ENABLED=1 TAIGI_TTS_DRAFT_MODE=1 \
 TAIGI_DYNAMIC_DRAFT=1 python -m uvicorn integrated_app_home_restored:app \
 --host 127.0.0.1 --port 8006 --reload

A SEPARATE local entrypoint: previous clinic integration files are left intact.
"""
from copy import copy
from fastapi import Request
from fastapi.responses import JSONResponse
from integrated_app_voice import app as voice_app
from integrated_clinic_routes import router as legacy_clinic_router
from integrated_home_restore_routes import router as restored_home_router

app = copy(voice_app)
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

# Explicit homepage/clinic-safe routes take precedence over old generic pages.
start = len(app.router.routes)
app.include_router(restored_home_router)
app.include_router(legacy_clinic_router)   # existing chooser, profile, source preview
restored = app.router.routes[start:]
del app.router.routes[start:]
app.router.routes[0:0] = restored


@app.middleware('http')
async def never_mix_clinic_data(request: Request, call_next):
    path = request.url.path
    method = request.method.upper()
    slug = request.query_params.get('clinic')
    loopback = request.client is not None and request.client.host in (
        '127.0.0.1','::1','localhost','testclient'
    )
    if path == '/api/booking/confirm' and method != 'OPTIONS':
        return JSONResponse({'detail':'本機雙診所預覽不接受正式預約，請勿輸入真實病患資料。'}, status_code=423)
    if path == '/api/self_pay' or path.startswith('/api/self_pay/'):
        # Only explicit Shanlin read-only lookups and stateless select/search.
        safe_get = (path in ('/api/self_pay/categories', '/api/self_pay/catalog') or
                    path.startswith('/api/self_pay/category/'))
        safe_post = path in ('/api/self_pay/search', '/api/self_pay/select')
        allowed = ((method == 'GET' and safe_get) or
                   (method == 'POST' and safe_post))
        if not (loopback and slug == 'shanlin' and allowed):
            return JSONResponse({'detail':'此目錄只可供山林本機唯讀查詢；頤典公版沒有自費資料。'}, status_code=423)
    if path == '/api/integrated/catalog' or path.startswith('/api/integrated/catalog/'):
        if not (loopback and slug == 'shanlin' and method == 'GET' and
                path == '/api/integrated/catalog/source'):
            return JSONResponse({'detail':'共用目錄僅供山林本機唯讀核對'}, status_code=423)
    # No clinic-free requests may access the legacy shared appointment DB.
    # Protected new routers serve neutral read-only config/availability/questions.
    if path in ('/api/clinic-config', '/api/availability', '/api/questions'):
        if not loopback or slug not in ('shanlin', 'yidian'):
            return JSONResponse({'detail':'缺少或不支援診所識別碼'}, status_code=423)
    return await call_next(request)
