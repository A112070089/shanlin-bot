"""Standalone 8017 fake Shanlin data source for local-only v3.6.2 tests."""
from fastapi import FastAPI
from shanlin_v362_source_router import create_router
from shanlin_readonly_sandbox_v361 import _SYNTHETIC

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(create_router(lambda: list(_SYNTHETIC)))
