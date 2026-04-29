from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError

from app.db.session import SessionLocal
from app.schemas.auth import AuthUser, WorkspaceBootstrapResponse
from app.schemas.folders import FolderEntry
from app.services.db_access import get_primary_user
from app.services.folders_service import (
    INBOX_FOLDER_ID,
    INBOX_FOLDER_NAME,
    get_folder_item_count,
    get_or_create_inbox_folder,
)
from app.services.store import STORE, seed_store


def _fallback_primary_user() -> dict[str, object]:
    seed_store()
    return next(iter(STORE.users.values()))


def current_user() -> AuthUser:
    try:
        with SessionLocal() as session:
            user = get_primary_user(session)
            session.commit()
            return AuthUser(id=str(user.id), username=user.username, created_at=user.created_at)
    except SQLAlchemyError:
        user = _fallback_primary_user()
        return AuthUser(
            id=str(user["id"]),
            username=str(user["username"]),
            created_at=user["created_at"],
        )


def bootstrap_workspace() -> WorkspaceBootstrapResponse:
    try:
        with SessionLocal() as session:
            inbox = get_or_create_inbox_folder(session)
            user = get_primary_user(session)
            session.commit()
            return WorkspaceBootstrapResponse(
                default_inbox_folder=FolderEntry(
                    id=str(inbox.id),
                    name=inbox.name,
                    is_builtin=True,
                    item_count=get_folder_item_count(session, inbox),
                    created_at=inbox.created_at,
                    updated_at=inbox.updated_at,
                ),
                primary_user=AuthUser(
                    id=str(user.id),
                    username=user.username,
                    created_at=user.created_at,
                ),
            )
    except SQLAlchemyError:
        user = _fallback_primary_user()
        return WorkspaceBootstrapResponse(
            default_inbox_folder=FolderEntry(
                id=INBOX_FOLDER_ID,
                name=INBOX_FOLDER_NAME,
                is_builtin=True,
                item_count=0,
            ),
            primary_user=AuthUser(
                id=str(user["id"]),
                username=str(user["username"]),
                created_at=user["created_at"],
            ),
        )
