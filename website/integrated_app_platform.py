"""Phase 8 engineering console on top of the already-tested local 8006 app.

Run from website/: python -m uvicorn integrated_app_platform:app --host 127.0.0.1 --port 8006 --reload
"""
from copy import copy
from integrated_app_home_restored import app as source_app
from platform_console import router as platform_router

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

# New routes must precede legacy catch-all and generic /{filename} routes.
before = len(app.router.routes)
app.include_router(platform_router)
new_routes = app.router.routes[before:]
del app.router.routes[before:]
app.router.routes[0:0] = new_routes
