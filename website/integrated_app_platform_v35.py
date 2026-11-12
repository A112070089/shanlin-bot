"""DOUBTS v3.5 - separate safe read-only status for Shanlin LINE reminder scheduler.

Does NOT deploy the separately hosted shanlin-bot or send reminders.
"""
from copy import copy
from integrated_app_platform_v34 import app as source_app
from platform_line_routes_v35 import router as v35_router

app=copy(source_app)
app.router=type(source_app.router)(
    routes=list(source_app.router.routes),
    redirect_slashes=source_app.router.redirect_slashes,
    on_startup=list(source_app.router.on_startup),
    on_shutdown=list(source_app.router.on_shutdown),
    lifespan=source_app.router.lifespan_context,
    dependency_overrides_provider=source_app.router.dependency_overrides_provider,
    route_class=source_app.router.route_class,
)
app.user_middleware=list(source_app.user_middleware)
app.middleware_stack=None
app.openapi_schema=None
start=len(app.router.routes)
app.include_router(v35_router)
added=app.router.routes[start:]
del app.router.routes[start:]
app.router.routes[0:0]=added
