"""Phase 3 *preview-only* entrypoint for 8006.

Keeps integrated_app.py and its booking/voice/pilot APIs unchanged.
Adds catalog consistency and a protected published-catalog mapping preview.
No new write endpoints, no automatic sync, no price/category overrides.
"""
from integrated_app_catalog import app
from integrated_release_routes import router as release_router

app.include_router(release_router)
app.openapi_schema = None
