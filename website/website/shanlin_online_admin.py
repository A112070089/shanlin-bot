"""Railway-only Shanlin administration adapter. Does not load local preview apps."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

import pilot_backend as backend
from platform_shanlin_unified_ui import unified_index, unified_script, unified_css, unified_frame

NO_CACHE = {'Cache-Control': 'no-store, private', 'Pragma': 'no-cache',
            'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'same-origin'}
API = '/api/pilot'
# Exclude platform provisioning, Yidian and demo-booking routes entirely.
ALLOWED = {
    API+'/admin/login', API+'/admin/legacy-shanlin-login', API+'/admin/session',
    API+'/admin/logout', API+'/admin/change-password', API+'/admin/state',
    API+'/admin/config', API+'/admin/staff', API+'/admin/shanlin/source-catalog',
    API+'/admin/import-excel', API+'/admin/catalog/draft', API+'/admin/catalog/publish',
    API+'/admin/integration', API+'/admin/health',
}
STORED_MUTATIONS = {API+'/admin/staff', API+'/admin/import-excel',
                    API+'/admin/catalog/draft', API+'/admin/catalog/publish'}


def _persistent_storage_ready():
    if backend.clinic_storage_mode('shanlin') == 'firebase':
        return bool(os.getenv('PILOT_SHANLIN_FIREBASE_URL') and
                    os.getenv('PILOT_SHANLIN_FIREBASE_CREDENTIALS'))
    mount = os.getenv('RAILWAY_VOLUME_MOUNT_PATH', '').strip()
    configured = os.getenv('PILOT_DATA_DIR', '').strip()
    if not mount or not configured:
        return False
    target, volume = Path(configured).resolve(), Path(mount).resolve()
    return target.is_relative_to(volume)


def _verified_shanlin(sess):
    if (sess.get('clinic') != 'shanlin' or sess.get('role') != 'clinic_admin'
            or (sess.get('legacyConfig') or {}).get('name') != '山林診所'):
        raise HTTPException(403, '僅限已驗證的山林診所管理員')
    return sess


async def _online_request(request: Request):
    # Reject a different tenant before any account lookup or upstream login.
    if request.query_params.get('clinic', 'shanlin') != 'shanlin':
        raise HTTPException(404, '此網站僅提供山林診所服務')
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        if 'application/json' in request.headers.get('content-type', ''):
            try:
                body = await request.json()
            except ValueError:
                body = None  # Normal FastAPI validation will report invalid JSON.
            if isinstance(body, dict) and body.get('clinicId', 'shanlin') != 'shanlin':
                raise HTTPException(404, '此網站僅提供山林診所服務')
        if request.url.path in STORED_MUTATIONS and not _persistent_storage_ready():
            raise HTTPException(503, '後台永久儲存尚未設定，請先完成設定後再儲存')


def _index():
    html = unified_index()
    html = html.replace('<title>頤典｜診所管理後台 v5</title>', '<title>山林診所｜管理後台</title>')
    html = html.replace('/pilot/assets/pilot.css?v=8', '/pilot/assets/pilot.css?v=shanlin-online-1')
    html = html.replace('/pilot/assets/pilot.js?v=10', '/pilot/assets/pilot.js?v=shanlin-online-1')
    # Retain dormant DOM elements used by the shared script, but never present
    # tenant selection, Yidian, or platform administration in this online adapter.
    html = html.replace('</head>', '''<style>
#chooser,#clinicView,#yidianLoginBlock,#platformLogin,#platformView,
#pilotEngineerEntry,#navClinics,#navPlatform {display:none!important}
</style></head>''')
    html = html.replace('請勿把其他診所的密碼輸入此頁；目前僅限本機示範，尚未連接正式預約與病歷資料。',
                        '請核對山林診所網站網址後再登入。')
    html = html.replace('href="/pilot"', 'href="/pilot?clinic=shanlin&view=admin"')
    return html


def _script():
    script = unified_script()
    anchor = "  const api='/api/pilot';"
    if script.count(anchor) != 1:
        raise RuntimeError('pilot.js API anchor changed; review online adapter')
    script = script.replace(anchor, anchor + """
  // The public website remains the existing Shanlin appointment homepage.
  const onlineArgs=new URLSearchParams(location.search);
  if(onlineArgs.get('clinic')!=='shanlin'||onlineArgs.get('view')!=='admin'){
    history.replaceState({},'', '/pilot?clinic=shanlin&view=admin');
  }
""", 1)
    script = script.replace("document.title=(clinic?CLINIC[clinic]+'｜':'')+'頤典公版示範';",
                            "document.title='山林診所｜管理後台';")
    return script


def install(app):
    if getattr(app.state, 'shanlin_online_admin_installed', False):
        return
    app.state.shanlin_online_admin_installed = True
    # Fixed upstream identity. No caller-supplied hosts or database URLs.
    os.environ.setdefault('PILOT_SHANLIN_LEGACY_AUTH', '1')
    os.environ.setdefault('PILOT_SHANLIN_LEGACY_URL',
                          'https://shanlin-bot-production.up.railway.app/api/admin/login')

    # This module is imported only by railway_app, so local cookie settings stay
    # unchanged. HTTPS-only cookies remain secure behind the Railway proxy.
    def online_cookie(request, response, token):
        response.set_cookie(backend.COOKIE, token, max_age=backend.AUTH_TTL,
                            httponly=True, secure=True, samesite='strict', path=API)
    backend.issue_cookie = online_cookie

    app.add_middleware(_OnlineBoundary)
    shared = APIRouter()
    shared.routes = [route for route in backend.router.routes
                     if getattr(route, 'path', '') in ALLOWED]
    app.include_router(shared, dependencies=[Depends(_online_request)], include_in_schema=False)
    routes = APIRouter(dependencies=[Depends(_online_request)])

    @routes.get('/pilot', include_in_schema=False)
    @routes.get('/pilot/', include_in_schema=False)
    def portal(request: Request):
        if request.query_params.get('view') == 'platform':
            raise HTTPException(404)
        if (request.query_params.get('clinic') != 'shanlin'
                or request.query_params.get('view') != 'admin'):
            return RedirectResponse('/pilot?clinic=shanlin&view=admin', status_code=303)
        return HTMLResponse(_index(), headers=NO_CACHE)

    @routes.get('/pilot/assets/pilot.js', include_in_schema=False)
    def javascript():
        return Response(_script(), media_type='text/javascript', headers=NO_CACHE)

    @routes.get('/pilot/assets/pilot.css', include_in_schema=False)
    def stylesheet():
        return Response(unified_css(), media_type='text/css', headers=NO_CACHE)

    @routes.get(API+'/admin/shanlin/booking-frame', include_in_schema=False)
    def frame(sess=Depends(backend.require_clinic)):
        _verified_shanlin(sess)
        csp = ("default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
               "connect-src 'self'; base-uri 'none'; img-src 'none'; form-action 'none'; "
               "frame-ancestors 'self'")
        return HTMLResponse(unified_frame(), headers={**NO_CACHE, 'Content-Security-Policy': csp})

    @routes.get(API+'/admin/shanlin/booking-stage/appointments', include_in_schema=False)
    def appointments(sess=Depends(backend.require_clinic)):
        return JSONResponse(backend.fetch_shanlin_live_appointments(_verified_shanlin(sess)),
                            headers=NO_CACHE)

    @routes.api_route(API+'/{unused:path}', methods=['GET','POST','PUT','PATCH','DELETE'],
                      include_in_schema=False)
    def unavailable(unused: str):
        raise HTTPException(404, '此功能未在線上山林網站開放')

    app.include_router(routes)


class _OnlineBoundary:
    """Apply online restrictions before the final StaticFiles fallback."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        request = Request(scope)
        parts = [part for part in scope.get('path', '').split('/') if part]
        blocked = (request.query_params.get('clinic', 'shanlin') != 'shanlin'
                   or any(part in ('pilot_static', 'platform_static') for part in parts)
                   or (scope.get('path', '').startswith('/api/pilot/') and
                       scope.get('method') in ('POST','PUT','PATCH','DELETE') and
                       request.headers.get('origin') and
                       request.headers['origin'].rstrip('/') != str(request.base_url).rstrip('/')))
        if blocked:
            return await JSONResponse({'detail':'此入口未開放'}, status_code=404,
                                      headers=NO_CACHE)(scope, receive, send)
        async def no_cache(message):
            if message['type'] == 'http.response.start' and (
                    scope.get('path', '').startswith('/pilot') or
                    scope.get('path', '').startswith(API)):
                headers = [(k,v) for k,v in message.get('headers', [])
                           if k.lower() not in {name.lower().encode() for name in NO_CACHE}]
                headers.extend((k.lower().encode(), v.encode()) for k,v in NO_CACHE.items())
                message['headers'] = headers
            await send(message)
        await self.app(scope, receive, no_cache)
