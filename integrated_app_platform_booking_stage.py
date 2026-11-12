"""Opt-in local preview; imports the EXISTING v3.6.3 DOUBTS app unchanged."""
from copy import copy
from integrated_app_platform_v363 import app as current_app
from platform_shanlin_booking_stage import router as staging_router

app = copy(current_app)
app.router = type(current_app.router)(
    routes=list(current_app.router.routes),
    redirect_slashes=current_app.router.redirect_slashes,
    on_startup=list(current_app.router.on_startup),
    on_shutdown=list(current_app.router.on_shutdown),
    lifespan=current_app.router.lifespan_context,
    dependency_overrides_provider=current_app.router.dependency_overrides_provider,
    route_class=current_app.router.route_class,
)
app.user_middleware = list(current_app.user_middleware)
app.middleware_stack = None
app.openapi_schema = None
count=len(app.router.routes)
app.include_router(staging_router)
routes=app.router.routes[count:]
del app.router.routes[count:]
app.router.routes[0:0]=routes
