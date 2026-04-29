from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import IntegrationSetting, ModelProvider, User

DEFAULT_WORKSPACE_USERNAME = "local"
DISABLED_PASSWORD_HASH = "single-user-mode"


def get_primary_user(session: Session) -> User:
    user = session.execute(select(User).order_by(User.created_at.asc())).scalar_one_or_none()
    if user is not None:
        return user

    user = User(
        username=DEFAULT_WORKSPACE_USERNAME,
        password_hash=DISABLED_PASSWORD_HASH,
        display_name="Local Workspace",
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
