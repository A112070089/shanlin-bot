"""Safe, additive routes for the Yidian local integration pilot.

Serve only known public pages and static assets, never the website directory itself.
The original website and admin pages are unchanged on disk.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, RedirectResponse

WEBSITE = Path(__file__).resolve().parent
PROJECT = WEBSITE.parent
PILOT_STATIC = WEBSITE / "pilot_static"
router = APIRouter()

SITE_PAGES = frozenset({
    "index.html", "appointment.html", "appointment2.html", "booking_success.html",
    "search.html",
})
SITE_FILES = frozenset({
    "clinic.js", "booking_questions.js", "self_pay_chat.js", "selfpay_panel.js",
    "yidian_speech.js", "yidian_taigi_stt.js", "yidian_elderly_voice.js",
    "yidian_speech.css", "yidian_taigi_stt.css",
    "yidian_elderly_voice.css", "yidian_senior_v14.css",
})
ASSET_EXTENSIONS = frozenset({
    ".css", ".js", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg",
    ".ico", ".woff", ".woff2", ".ttf", ".otf",
})


def _response(path: Path) -> FileResponse:
    if not path.is_file():
        raise HTTPException(404, "Public website file not found")
    return FileResponse(path, headers={"X-Content-Type-Options": "nosniff"})


def _public_asset(relative: str, bases: tuple[Path, ...]) -> FileResponse:
    normalized = Path(relative)
    if (not relative or relative.startswith("/") or "\\" in relative
            or any(part in (".", "..") or part.startswith(".") for part in normalized.parts)
            or normalized.suffix.lower() not in ASSET_EXTENSIONS):
        raise HTTPException(404)
    for base in bases:
        base = base.resolve()
        candidate = (base / normalized).resolve()
        if candidate.is_relative_to(base) and candidate.is_file():
            return _response(candidate)
    raise HTTPException(404, "Public static asset not found")


def _admin_backend_urls() -> tuple[str, str]:
    # Public web origins only; never embed any access token, password or key.
    local = os.getenv("INTEGRATED_LOCAL_ADMIN_API", "http://127.0.0.1:8001").rstrip("/")
    remote = os.getenv("INTEGRATED_REMOTE_ADMIN_API", "https://shanlin-bot-production.up.railway.app").rstrip("/")
    for value, expected in ((local, "http"), (remote, "https")):
        p = urlsplit(value)
        if p.scheme != expected or not p.hostname or p.username or p.password or p.query or p.fragment or p.path not in ("", "/"):
            raise RuntimeError("Invalid integrated admin API public origin")
    if urlsplit(local).hostname not in ("127.0.0.1", "localhost", "::1"):
        raise RuntimeError("Local admin API must point to localhost")
    return local, remote


@router.get("/integrated/health", include_in_schema=False)
def integration_health():
    return JSONResponse({
        "mode": "local_integration_preview",
        "bookingApi": "original_main",
        "pilotApi": "pilot_backend",
        "taigi": "local_only_external_8002_8003_8004_if_enabled",
        "legacyAdmin": "external_api_not_merged",
        "catalogSync": False,
        "productionReady": False,
    }, headers={"Cache-Control": "no-store"})


@router.get("/", include_in_schema=False)
@router.get("/index.html", include_in_schema=False)
def home_page():
    # The original home page contains one older bridge that still hard-codes
    # localhost:8000. Swap only that expression in memory for same-origin API.
    page = WEBSITE / "index.html"
    if not page.is_file():
        raise HTTPException(404, "Original homepage missing")
    html = page.read_text(encoding="utf-8")
    old = ('const api=local ? "http://127.0.0.1:8000" :\n'
           r'    String(window.SITE?.bookingApi || "").replace(/\/$/,"");')
    new = r'const api=String(window.SITE?.bookingApi || location.origin).replace(/\/$/,"");'
    html = html.replace(old, new)
    return HTMLResponse(html, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/admin.html", include_in_schema=False)
def legacy_admin_page():
    # In-memory link update only; the source file is never overwritten.
    source = PROJECT / "admin.html"
    if not source.is_file():
        raise HTTPException(404, "Original admin.html missing in project root")
    html = source.read_text(encoding="utf-8")
    html = html.replace("http://127.0.0.1:8005/pilot?clinic=shanlin&amp;view=admin",
                        "/pilot?clinic=shanlin&amp;view=admin")
    return HTMLResponse(html, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/site-config.js", include_in_schema=False)
def integrated_site_config():
    """Keep booking on current origin; keep legacy appointment admin on its own API."""
    local, remote = _admin_backend_urls()
    js = ("(function(){'use strict';"
          "const local=['127.0.0.1','localhost','::1'].includes(location.hostname);"
          "const root=location.origin;"
          "const config={bookingApi:root,adminApi:local?" + json.dumps(local) + ":" + json.dumps(remote)
          + ",adminPage:root+'/admin.html'};"
          "window.SITE_CONFIG=config;"
          "window.SITE={...config,isLocal:local,isIntegrated:true};"
          "})();")
    return Response(js, media_type="application/javascript", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/pilot", include_in_schema=False)
@router.get("/pilot/", include_in_schema=False)
def integrated_pilot_html():
    html_path = PILOT_STATIC / "index.html"
    if not html_path.is_file():
        raise HTTPException(404, "Pilot frontend missing")
    html = html_path.read_text(encoding="utf-8")
    html = html.replace("https://shanlin-bot-production.up.railway.app/admin.html", "/admin.html")
    html = html.replace("http://127.0.0.1:5500/admin.html", "/admin.html")
    return HTMLResponse(html, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/pilot/assets/pilot.js", include_in_schema=False)
def integrated_pilot_js():
    source = PILOT_STATIC / "pilot.js"
    if not source.is_file():
        raise HTTPException(404)
    js = source.read_text(encoding="utf-8")
    js = js.replace("https://shanlin-bot-production.up.railway.app/admin.html", "/admin.html")
    return Response(js, media_type="application/javascript", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/assets/{asset_path:path}", include_in_schema=False)
def website_assets(asset_path: str):
    return _public_asset(asset_path, (WEBSITE / "assets", PROJECT / "assets"))


@router.get("/css/{asset_path:path}", include_in_schema=False)
def project_styles(asset_path: str):
    return _public_asset(asset_path, (PROJECT / "css", WEBSITE / "css"))


@router.get("/js/{asset_path:path}", include_in_schema=False)
def project_scripts(asset_path: str):
    return _public_asset(asset_path, (PROJECT / "js", WEBSITE / "js"))


@router.get("/favicon.ico", include_in_schema=False)
def favicon():
    return _public_asset("favicon/favicon.png", (WEBSITE / "assets", PROJECT / "assets"))


@router.get("/{filename}", include_in_schema=False)
def public_single_file(filename: str):
    if filename in SITE_PAGES:
        return _response(WEBSITE / filename)
    if filename in SITE_FILES:
        # admin.html from the original root may use its own clinic.js.
        locations = (PROJECT / filename, WEBSITE / filename) if filename == "clinic.js" else (WEBSITE / filename, PROJECT / filename)
        for path in locations:
            if path.is_file():
                return _response(path)
    raise HTTPException(404, "Resource is not a public website file")
