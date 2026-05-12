from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import User
from app.db.session import SessionLocal
from app.schemas.auth import (
    AuthLoginRequest,
    AuthRegisterRequest,
    AuthSessionResponse,
    AuthUser,
    WorkspaceBootstrapResponse,
)
from app.schemas.folders import FolderEntry
from app.services.db_access import get_primary_user
from app.services.folders_service import (
    INBOX_FOLDER_ID,
    INBOX_FOLDER_NAME,
    get_folder_item_count,
    get_or_create_inbox_folder,
)
from app.services.passwords import hash_password, verify_password
from app.services.store import STORE, seed_store
from app.services.tokens import create_auth_token


def _fallback_primary_user() -> dict[str, object]:
    seed_store()
    return next(iter(STORE.users.values()))


def current_user() -> AuthUser:
    try:
        with SessionLocal() as session:
            user = get_primary_user(session)
            session.commit()
            return _to_auth_user(user)
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
                    email=user.email,
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


def login(payload: AuthLoginRequest) -> AuthSessionResponse:
    identifier = payload.identifier.strip()
    if not identifier:
        raise ValueError("请输入用户名或邮箱")
    normalized_email = identifier.lower()

    with SessionLocal() as session:
        get_primary_user(session)
        user = session.execute(
            select(User)
            .where(
                or_(
                    func.lower(User.username) == identifier.lower(),
                    func.lower(User.email) == normalized_email,
                )
            )
            .limit(1)
        ).scalar_one_or_none()
        if user is None or not verify_password(payload.password, user.password_hash):
            raise ValueError("用户名或密码不正确")
        session.commit()
        return AuthSessionResponse(token=create_auth_token(user.id), user=_to_auth_user(user))


def register(payload: AuthRegisterRequest) -> AuthSessionResponse:
    username = payload.username.strip()
    email = payload.email.strip().lower() if payload.email else None
    if not username:
        raise ValueError("请输入用户名")
    if "@" in username:
        raise ValueError("用户名不能使用邮箱格式")

    with SessionLocal() as session:
        get_primary_user(session)
        conditions = [func.lower(User.username) == username.lower()]
        if email:
            conditions.append(func.lower(User.email) == email)
        existing = session.execute(
            select(User).where(or_(*conditions)).limit(1)
        ).scalar_one_or_none()
        if existing is not None:
            raise ValueError("用户名或邮箱已存在")
        user = User(
            username=username,
            email=email,
            password_hash=hash_password(payload.password),
            display_name=username,
        )
        session.add(user)
        session.flush()
        session.commit()
        return AuthSessionResponse(token=create_auth_token(user.id), user=_to_auth_user(user))


def _to_auth_user(user: User) -> AuthUser:
    return AuthUser(
        id=str(user.id),
        username=user.username,
        email=user.email,
        created_at=user.created_at,
    )
