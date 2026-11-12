"""Authenticated, read-only preview of a Shanlin catalog release mapping."""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

import pilot_backend
from integrated_release_validation import load_source, preview_published_release

router = APIRouter()


@router.get('/api/integrated/admin/catalog/release-preview', include_in_schema=False)
def release_preview(sess=Depends(pilot_backend.require_clinic)):
    if sess.get('clinic') != 'shanlin':
        raise HTTPException(403, '此階段只支援山林診所整合檢查')
    try:
        source, source_hash = load_source(Path(__file__).resolve().parent)
    except (OSError, ValueError) as exc:
        raise HTTPException(503, str(exc)) from exc
    # Read only. Never return drafts or private appointment records.
    published = pilot_backend.store().read('shanlin', 'catalog_published')
    result = preview_published_release(source, published, source_hash)
    return JSONResponse(result, headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
