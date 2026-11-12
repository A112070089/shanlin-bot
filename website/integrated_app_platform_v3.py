"""V3 local staged clinic onboarding layered on V2.1 without replacing old routes.

Run from website/: python -m uvicorn integrated_app_platform_v3:app --host 127.0.0.1 --port 8006 --reload
"""
from copy import copy
from integrated_app_platform_v2 import app as source_app
from platform_onboarding_routes_v3 import router as onboarding_router

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

before = len(app.router.routes)
app.include_router(onboarding_router)
new_routes = app.router.routes[before:]
del app.router.routes[before:]
app.router.routes[0:0] = new_routes
