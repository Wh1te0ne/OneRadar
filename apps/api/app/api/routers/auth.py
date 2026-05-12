from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import require_current_user
from app.schemas.auth import (
    AuthLoginRequest,
    AuthRegisterRequest,
    AuthSessionResponse,
    AuthUser,
    WorkspaceBootstrapResponse,
)
from app.services.auth_service import bootstrap_workspace as bootstrap_workspace_service
from app.services.auth_service import current_user
from app.services.auth_service import login as login_service
from app.services.auth_service import register as register_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", dependencies=[Depends(require_current_user)])
def me() -> AuthUser:
    return current_user()


@router.get("/bootstrap")
def bootstrap_workspace() -> WorkspaceBootstrapResponse:
    return bootstrap_workspace_service()


@router.post("/login")
def login(payload: AuthLoginRequest) -> AuthSessionResponse:
    try:
        return login_service(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/register")
def register(payload: AuthRegisterRequest) -> AuthSessionResponse:
    try:
        return register_service(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
