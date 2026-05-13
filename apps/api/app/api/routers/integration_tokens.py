from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import require_current_user
from app.schemas.integration_tokens import (
    IntegrationTokenCreateRequest,
    IntegrationTokenCreateResponse,
    IntegrationTokenListResponse,
    IntegrationTokenRevokeResponse,
)
from app.services.integration_tokens import (
    create_integration_token as create_integration_token_service,
)
from app.services.integration_tokens import (
    list_integration_tokens as list_integration_tokens_service,
)
from app.services.integration_tokens import (
    revoke_integration_token as revoke_integration_token_service,
)

router = APIRouter(
    prefix="/integration-tokens",
    tags=["integration-tokens"],
    dependencies=[Depends(require_current_user)],
)


@router.get("")
def list_integration_tokens() -> IntegrationTokenListResponse:
    return list_integration_tokens_service()


@router.post("")
def create_integration_token(payload: IntegrationTokenCreateRequest) -> IntegrationTokenCreateResponse:
    try:
        return create_integration_token_service(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{token_id}")
def revoke_integration_token(token_id: str) -> IntegrationTokenRevokeResponse:
    try:
        return revoke_integration_token_service(token_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
