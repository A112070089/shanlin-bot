"""v3.6.3: add-only, locally scoped integration onto existing 8006 platform."""
from copy import copy
from integrated_app_platform_v362 import app as prior_app
from platform_shanlin_booking_routes_v363 import router as added_router

app = copy(prior_app)
app.router = type(prior_app.router)(
    routes=list(prior_app.router.routes),
    redirect_slashes=prior_app.router.redirect_slashes,
    on_startup=list(prior_app.router.on_startup),
    on_shutdown=list(prior_app.router.on_shutdown),
    lifespan=prior_app.router.lifespan_context,
    dependency_overrides_provider=prior_app.router.dependency_overrides_provider,
    route_class=prior_app.router.route_class,
)
app.user_middleware = list(prior_app.user_middleware)
app.middleware_stack = None
app.openapi_schema = None
start = len(app.router.routes)
app.include_router(added_router)
new = app.router.routes[start:]
del app.router.routes[start:]
app.router.routes[0:0] = new
