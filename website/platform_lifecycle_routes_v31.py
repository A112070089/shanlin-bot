"""Engineer-only API for archive/restore and guarded V2/V3 draft purge."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from platform_console import NO_CACHE, platform_read, platform_write
import platform_clinic_registry as registry
import platform_lifecycle_store_v31 as lifecycle

router = APIRouter()
PREFIX = '/api/pilot/platform/console/clinic-registry/drafts'


class Lifecycle(BaseModel):
    disabled: bool
    expectedRevision: str = Field(pattern=r'^[0-9a-f]{32}$')


class Purge(BaseModel):
    confirmation: str = Field(min_length=3, max_length=32)
    expectedRegistryRevision: str = Field(pattern=r'^[0-9a-f]{32}$')
    expectedOnboardingRevision: str = Field(pattern=r'^[0-9a-f]{32}$')


@router.get(PREFIX+'/{clinic_id}/deletion-check', include_in_schema=False)
def get_check(clinic_id: str, sess=Depends(platform_read)):
    try:
        return JSONResponse(lifecycle.deletion_check(clinic_id), headers=NO_CACHE)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post(PREFIX+'/{clinic_id}/lifecycle', include_in_schema=False)
def change_state(clinic_id: str, body: Lifecycle, sess=Depends(platform_write)):
    try:
        state = lifecycle.set_disabled(slug=clinic_id, disabled=body.disabled,
                                       expected_revision=body.expectedRevision,
                                       actor=sess['username'])
        return JSONResponse({'success': True, 'registry': state}, headers=NO_CACHE)
    except registry.RevisionConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete(PREFIX+'/{clinic_id}', include_in_schema=False)
def permanently_delete(clinic_id: str, body: Purge, sess=Depends(platform_write)):
    try:
        return JSONResponse(lifecycle.purge(
            slug=clinic_id, confirmation=body.confirmation,
            registry_revision=body.expectedRegistryRevision,
            onboarding_revision=body.expectedOnboardingRevision,
            actor=sess['username']), headers=NO_CACHE)
    except registry.RevisionConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except lifecycle.DeletionBlocked as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
