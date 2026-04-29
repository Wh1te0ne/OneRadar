from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import ModelProvider
from app.db.session import SessionLocal
from app.schemas.common import ProviderType
from app.services.credential_crypto import reveal_secret
from app.services.db_access import get_model_provider
from app.services.store import STORE, seed_store


class ProviderCapability(StrEnum):
    summarization = "summarization"
    embedding = "embedding"
    transcription = "transcription"
    video_visual_understanding = "video_visual_understanding"


@dataclass(frozen=True, slots=True)
class ProviderRuntimeConfig:
    provider_id: str
    provider_name: str
    provider_type: ProviderType
    base_url: str | None
    api_key: str | None
    model_name: str | None
    capability: ProviderCapability


def _model_for_capability(
    capability: ProviderCapability,
    *,
    chat_model: str | None,
    embedding_model: str | None,
    transcription_model: str | None,
) -> str | None:
    if capability == ProviderCapability.embedding:
        return embedding_model
    if capability == ProviderCapability.transcription:
        return transcription_model
    return chat_model


def _config_from_model(
    provider: ModelProvider,
    capability: ProviderCapability,
) -> ProviderRuntimeConfig:
    return ProviderRuntimeConfig(
        provider_id=str(provider.id),
        provider_name=provider.provider_name,
        provider_type=ProviderType(provider.provider_type),
        base_url=provider.base_url,
        api_key=reveal_secret(provider.api_key_encrypted),
        model_name=_model_for_capability(
            capability,
            chat_model=provider.chat_model,
            embedding_model=provider.embedding_model,
            transcription_model=provider.transcription_model,
        ),
        capability=capability,
    )


def _config_from_record(
    record: dict[str, object],
    capability: ProviderCapability,
) -> ProviderRuntimeConfig:
    return ProviderRuntimeConfig(
        provider_id=str(record["id"]),
        provider_name=str(record["provider_name"]),
        provider_type=ProviderType(record["provider_type"]),
        base_url=record.get("base_url"),
        api_key=reveal_secret(record.get("api_key_encrypted")),
        model_name=_model_for_capability(
            capability,
            chat_model=record.get("chat_model"),
            embedding_model=record.get("embedding_model"),
            transcription_model=record.get("transcription_model"),
        ),
        capability=capability,
    )


def resolve_provider_config(
    provider_id: str | None,
    capability: ProviderCapability,
) -> ProviderRuntimeConfig:
    try:
        with SessionLocal() as session:
            provider = get_model_provider(session, provider_id or "")
            if provider is None and provider_id and provider_id in STORE.providers:
                return _config_from_record(STORE.providers[provider_id], capability)
            if provider is None:
                provider = (
                    session.execute(
                        select(ModelProvider)
                        .where(ModelProvider.is_enabled.is_(True))
                        .order_by(ModelProvider.created_at.asc())
                    )
                    .scalars()
                    .first()
                )
            if provider is None:
                raise ValueError("provider not found")
            return _config_from_model(provider, capability)
    except SQLAlchemyError:
        seed_store()
        record = STORE.providers.get(provider_id or "")
        if record is None:
            record = next(
                (item for item in STORE.providers.values() if bool(item.get("is_enabled", True))),
                None,
            )
        if record is None:
            raise ValueError("provider not found") from None
        return _config_from_record(record, capability)
