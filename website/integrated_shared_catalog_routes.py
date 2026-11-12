"""Public-safe, original-source-only read-only catalog preview endpoint."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from integrated_shared_catalog import SharedCatalogUnavailable, make_shared_catalog

router = APIRouter()


@router.get('/api/integrated/catalog/source', include_in_schema=False)
def shared_catalog_source():
    try:
        data = make_shared_catalog()
    except (SharedCatalogUnavailable, OSError, ValueError) as exc:
        # Do not leak local paths / database details in public error text.
        raise HTTPException(503, '原預約目錄版本不一致，暫停共用資料查詢') from exc
    return JSONResponse(data, headers={
        'Cache-Control': 'no-store',
        'X-Content-Type-Options': 'nosniff',
    })
