"""Phase 5 local 8006 preview: real booking UI checks the shared catalog.

The same pre-existing /api/self_pay/* APIs still determine items, prices,
medical descriptions, and bookings. Taigi receives only validated item context.
No write/publish/Firebase paths or original source files are changed.
"""
from integrated_app_shared import app
from integrated_booking_page import router as booking_check_router

# The original site has a generic GET /{filename} route. Insert the exact
# checked appointment route before it without changing the original router.
existing_route_count = len(app.router.routes)
app.include_router(booking_check_router)
new_routes = app.router.routes[existing_route_count:]
del app.router.routes[existing_route_count:]
app.router.routes[0:0] = new_routes
app.openapi_schema = None
