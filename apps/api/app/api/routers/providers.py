from fastapi import APIRouter, HTTPException

from app.schemas.providers import (
    ProviderCreateRequest,
    ProviderDeleteResponse,
    ProviderEntry,
    ProviderListResponse,
    ProviderPresetEntry,
    ProviderTestResponse,
    ProviderUpdateRequest,
)
from app.services.providers_service import create_provider as create_provider_service
from app.services.providers_service import delete_provider as delete_provider_service
from app.services.providers_service import list_presets as list_presets_service
from app.services.providers_service import list_providers as list_providers_service
from app.services.providers_service import test_provider as test_provider_service
from app.services.providers_service import update_provider as update_provider_service

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("")
def list_providers() -> ProviderListResponse:
    return list_providers_service()


@router.post("")
def create_provider(payload: ProviderCreateRequest) -> ProviderEntry:
    try:
        return create_provider_service(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{provider_id}")
def update_provider(provider_id: str, payload: ProviderUpdateRequest) -> ProviderEntry:
    try:
        return update_provider_service(provider_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{provider_id}")
def delete_provider(provider_id: str) -> ProviderDeleteResponse:
    return delete_provider_service(provider_id)


@router.post("/{provider_id}/test")
def test_provider(provider_id: str) -> ProviderTestResponse:
    return test_provider_service(provider_id)


@router.get("/presets")
def provider_presets() -> list[ProviderPresetEntry]:
    return list_presets_service()
