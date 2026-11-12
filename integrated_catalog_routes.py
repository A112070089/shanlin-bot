"""Read-only status route, without editing original self-pay or pilot APIs."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from integrated_catalog_validation import reconcile

router = APIRouter()

@router.get('/integrated/catalog-consistency', include_in_schema=False)
def catalog_consistency():
    report = reconcile()
    return JSONResponse(report, headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
