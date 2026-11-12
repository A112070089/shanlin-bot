"""Phase 4 integration entrypoint: original-source catalog data contract.

No existing routes, pricing, original JSON, Firebase, or Taiwanese speech
models are modified. This endpoint is a technical PREVIEW, not a production
catalog release or a booking-source migration.
"""
from integrated_app_release import app
from integrated_shared_catalog_routes import router as shared_catalog_router

app.include_router(shared_catalog_router)
app.openapi_schema = None
