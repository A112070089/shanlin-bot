"""8019-only staff UX preview; preserves existing v3.6.3 and v3.6.5 routes.

New *opt-in* app entrypoint. No permanent changes to site or staging backend.
"""
from copy import copy
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from integrated_app_platform_booking_stage import app as base_app
import pilot_backend as backend
from platform_console import local_only, NO_CACHE
from platform_shanlin_booking_stage import _shanlin_session
from platform_shanlin_unified_ui import unified_index, unified_script, unified_css, unified_frame

app = copy(base_app)
app.router = type(base_app.router)(
    routes=list(base_app.router.routes),
    redirect_slashes=base_app.router.redirect_slashes,
    on_startup=list(base_app.router.on_startup),
    on_shutdown=list(base_app.router.on_shutdown),
    lifespan=base_app.router.lifespan_context,
    dependency_overrides_provider=base_app.router.dependency_overrides_provider,
    route_class=base_app.router.route_class,
)
app.user_middleware = list(base_app.user_middleware)
app.middleware_stack = None
app.openapi_schema = None
routes = APIRouter()
HEADERS = {**NO_CACHE, 'Pragma': 'no-cache'}

@routes.get('/pilot', include_in_schema=False)
@routes.get('/pilot/', include_in_schema=False)
def pilot_index(request: Request):
    local_only(request)
    return HTMLResponse(unified_index(), headers=HEADERS)

@routes.get('/pilot/assets/pilot.js', include_in_schema=False)
def pilot_script(request: Request):
    local_only(request)
    return Response(unified_script(), media_type='text/javascript', headers=HEADERS)

@routes.get('/pilot/assets/pilot.css', include_in_schema=False)
def pilot_styles(request: Request):
    local_only(request)
    return Response(unified_css(), media_type='text/css', headers=HEADERS)

@routes.get('/api/pilot/admin/shanlin/booking-frame', include_in_schema=False)
def booking_frame(request: Request, sess=Depends(backend.require_clinic)):
    _shanlin_session(request, sess)
    # Same-origin ONLY: a session-authenticated iframe inside the clinic pane.
    csp = ("default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
           "connect-src 'self'; base-uri 'none'; img-src 'none'; form-action 'none'; "
           "frame-ancestors 'self'")
    return HTMLResponse(unified_frame(), headers={**HEADERS,'Content-Security-Policy':csp,'X-Content-Type-Options':'nosniff'})

start = len(app.router.routes)
app.include_router(routes)
added = app.router.routes[start:]
del app.router.routes[start:]
app.router.routes[:0] = added
