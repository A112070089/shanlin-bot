"""DOUBTS v3.6.1: v3.6 plus scoped read-only synthetic Shanlin booking bridge.

Only listen on 127.0.0.1; engineer console MUST NOT be exposed publicly.
"""
from copy import copy
from integrated_app_platform_v36 import app as source_app
from platform_shanlin_booking_routes_v361 import router as booking_router

app = copy(source_app)
app.router = type(source_app.router)(
    routes=list(source_app.router.routes),
    redirect_slashes=source_app.router.redirect_slashes,
    on_startup=list(source_app.router.on_startup),
    on_shutdown=list(source_app.router.on_shutdown),
    lifespan=source_app.router.lifespan_context,
    dependency_overrides_provider=source_app.router.dependency_overrides_provider,
    route_class=source_app.router.route_class,
)
app.user_middleware = list(source_app.user_middleware)
app.middleware_stack = None
app.openapi_schema = None
start = len(app.router.routes)
app.include_router(booking_router)
added = app.router.routes[start:]
del app.router.routes[start:]
app.router.routes[0:0] = added
