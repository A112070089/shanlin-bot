"""Phase 2 entrypoint: add a read-only catalog audit to the existing 8006 app.

Does not change integrated_app.py or existing booking / pilot business rules.
"""
from integrated_app import app
from integrated_catalog_routes import router as catalog_validation_router

app.include_router(catalog_validation_router)
app.openapi_schema = None
