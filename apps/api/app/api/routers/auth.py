from fastapi import APIRouter

from app.schemas.auth import AuthUser, WorkspaceBootstrapResponse
from app.services.auth_service import bootstrap_workspace as bootstrap_workspace_service
from app.services.auth_service import current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
def me() -> AuthUser:
    return current_user()


@router.get("/bootstrap")
def bootstrap_workspace() -> WorkspaceBootstrapResponse:
    return bootstrap_workspace_service()
