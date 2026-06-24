from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import require_current_user
from app.schemas.integration_tokens import (
    IntegrationTokenCreateRequest,
    IntegrationTokenCreateResponse,
    IntegrationTokenEntry,
    IntegrationTokenListResponse,
    IntegrationTokenRevokeResponse,
    IntegrationTokenUpdateRequest,
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
from app.services.integration_tokens import (
    update_integration_token as update_integration_token_service,
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
def create_integration_token(
    payload: IntegrationTokenCreateRequest,
) -> IntegrationTokenCreateResponse:
    try:
        return create_integration_token_service(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{token_id}")
def update_integration_token(
    token_id: str,
    payload: IntegrationTokenUpdateRequest,
) -> IntegrationTokenEntry:
    try:
        return update_integration_token_service(token_id, payload)
    except ValueError as exc:
        message = str(exc)
        status_code = 400 if message == "请输入令牌名称" else 404
        raise HTTPException(status_code=status_code, detail=message) from exc


@router.delete("/{token_id}")
def revoke_integration_token(token_id: str) -> IntegrationTokenRevokeResponse:
    try:
        return revoke_integration_token_service(token_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
