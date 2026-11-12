"""Add a safe clinic draft center on top of engineer console v1.

In website/: python -m uvicorn integrated_app_platform_v2:app --host 127.0.0.1 --port 8006 --reload
"""
from copy import copy
from integrated_app_platform import app as source_app
from platform_clinic_routes import router as onboarding_router

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

# Ensure the v2 dashboard override and draft routes precede v1 + catch-all.
start = len(app.router.routes)
app.include_router(onboarding_router)
new = app.router.routes[start:]
del app.router.routes[start:]
app.router.routes[0:0] = new
