"""DOUBTS v3.3: software release and acceptance records, on v3.2.1.

Run from website/: python -m uvicorn integrated_app_platform_v33:app --host 127.0.0.1 --port 8006 --reload
Does NOT deploy programs, send reminders, or enable patient functionality.
"""
from copy import copy
from integrated_app_platform_v321 import app as source_app
from platform_release_routes_v33 import router as release_router

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
app.include_router(release_router)
new = app.router.routes[start:]
del app.router.routes[start:]
app.router.routes[0:0] = new
