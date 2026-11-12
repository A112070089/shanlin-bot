"""Local phase 6: phase 5 booking app plus diagnostic-only voice routes.

Run with TAIGI_STT_ENABLED=1 TAIGI_TTS_ENABLED=1
TAIGI_TTS_DRAFT_MODE=1 TAIGI_DYNAMIC_DRAFT=1, and the existing
local 8002/8003/8004 services. Do not deploy this diagnostic app publicly.
"""
from integrated_app_booking import app
from integrated_voice_diagnostics import router as voice_router

# Original static file route and general catch-all must not shadow diagnostics.
old_count = len(app.router.routes)
app.include_router(voice_router)
new_routes = app.router.routes[old_count:]
del app.router.routes[old_count:]
app.router.routes[0:0] = new_routes
app.openapi_schema = None
