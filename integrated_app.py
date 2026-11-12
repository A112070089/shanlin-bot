"""Additive integration entrypoint, leaving main.py and pilot_app.py untouched.

Run inside the ORIGINAL website directory:
    python -m uvicorn integrated_app:app --host 127.0.0.1 --port 8006

This is a LOCAL TEST integration, not production deployment approval.
"""
from fastapi.routing import APIRoute
from contextlib import redirect_stdout
from io import StringIO

# The existing main.py logs a partial API-key prefix during import. Suppress
# only import-time stdout in this new entrypoint; exceptions still propagate.
with redirect_stdout(StringIO()):
    from main import app  # Original booking/self-pay/taigi routes are already registered.
from integrated_site import router as integrated_site_router
import pilot_backend

# Keep independent test-server login cookies from clashing with port 8005.
pilot_backend.COOKIE = "yidian_pilot_integrated_session"
pilot_router = pilot_backend.router

# A historical GET endpoint mutates the appointments database. Remove only this
# route in the integration entrypoint; a read-only GET must not write patient data.
app.router.routes[:] = [
    route for route in app.router.routes
    if not (isinstance(route, APIRoute) and route.path == "/api/firebase/test-write")
]
app.openapi_schema = None

# Specialized local HTML routes come first; pilot API routes are still delegated
# unchanged, including Firebase transactions and HTTP 409 conflict handling.
app.include_router(integrated_site_router)
app.include_router(pilot_router)
