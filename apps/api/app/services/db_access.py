from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import IntegrationSetting, ModelProvider, User
from app.services.passwords import hash_password
from app.services.user_context import get_current_user_id

DEFAULT_WORKSPACE_USERNAME = "whiteone"
DISABLED_PASSWORD_HASH = "single-user-mode"


def get_primary_user(session: Session) -> User:
    current_user_id = get_current_user_id()
    if current_user_id is not None:
        user = session.get(User, current_user_id)
        if user is not None:
            return user

    settings = get_settings()
    bootstrap_username = (settings.bootstrap_username or DEFAULT_WORKSPACE_USERNAME).strip() or DEFAULT_WORKSPACE_USERNAME
    bootstrap_email = settings.bootstrap_email.strip().lower() if settings.bootstrap_email else None
    user = session.execute(select(User).order_by(User.created_at.asc()).limit(1)).scalars().first()
    if user is not None:
        changed = False
        if user.username in {"local", ""} and bootstrap_username:
            user.username = bootstrap_username
            user.display_name = bootstrap_username
            changed = True
        if bootstrap_email and not user.email:
            user.email = bootstrap_email
            changed = True
        if (
            settings.bootstrap_password
            and (user.password_hash == DISABLED_PASSWORD_HASH or not user.password_hash.startswith("pbkdf2_sha256:"))
        ):
            user.password_hash = hash_password(settings.bootstrap_password)
            changed = True
        if changed:
            session.add(user)
            session.flush()
        return user

    user = User(
        username=bootstrap_username,
        email=bootstrap_email,
        password_hash=hash_password(settings.bootstrap_password) if settings.bootstrap_password else DISABLED_PASSWORD_HASH,
        display_name=bootstrap_username,
    )
    session.add(user)
    session.flush()
    return user


def get_model_provider(session: Session, provider_id: str) -> ModelProvider | None:
    try:
        provider_uuid = UUID(provider_id)
    except ValueError:
        return None
    return session.get(ModelProvider, provider_uuid)



def get_bilibili_integration_setting(session: Session) -> IntegrationSetting | None:
    user = get_primary_user(session)
    return session.execute(
        select(IntegrationSetting)
        .where(
            IntegrationSetting.user_id == user.id,
            IntegrationSetting.integration_key == 'bilibili',
        )
        .limit(1)
    ).scalar_one_or_none()
