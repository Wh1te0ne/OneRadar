from fastapi import APIRouter

from app.schemas.auth import AuthUser, LoginRequest, LoginResponse, LogoutResponse, WorkspaceBootstrapResponse
from app.services.auth_service import bootstrap_workspace as bootstrap_workspace_service
from app.services.auth_service import current_user, login as login_service, logout as logout_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(payload: LoginRequest) -> LoginResponse:
    return login_service(payload.username, payload.password)


@router.post("/logout")
def logout() -> LogoutResponse:
    return logout_service()


@router.get("/me")
def me() -> AuthUser:
    return current_user()


@router.get("/bootstrap")
def bootstrap_workspace() -> WorkspaceBootstrapResponse:
    return bootstrap_workspace_service()
