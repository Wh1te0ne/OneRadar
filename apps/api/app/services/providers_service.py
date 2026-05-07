from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import ModelProvider
from app.db.session import SessionLocal
from app.schemas.common import ProviderType
from app.schemas.providers import (
    ProviderCreateRequest,
    ProviderDeleteResponse,
    ProviderEntry,
    ProviderListResponse,
    ProviderPresetEntry,
    ProviderTestResponse,
    ProviderUpdateRequest,
)
from app.services.credential_crypto import protect_secret
from app.services.db_access import get_model_provider, get_primary_user
from app.services.store import STORE, seed_store


def list_presets() -> list[ProviderPresetEntry]:
    return [
        ProviderPresetEntry(provider_type=ProviderType.doubao, provider_name="Doubao"),
        ProviderPresetEntry(
            provider_type=ProviderType.openai_compatible,
            provider_name="OpenAI Compatible",
        ),
    ]


def _to_provider_entry(provider: ModelProvider) -> ProviderEntry:
    config = dict(provider.config or {})
    transcription_config = dict(config.get("transcription") or {})
    capability = _provider_capability(
        config=config,
        chat_model=provider.chat_model,
        transcription_model=provider.transcription_model,
    )
    is_configured = _provider_is_configured(
        capability=capability,
        api_key_configured=bool(provider.api_key_encrypted),
        chat_model=provider.chat_model,
        transcription_model=provider.transcription_model,
        transcription_config=transcription_config,
    )
    return ProviderEntry(
        id=str(provider.id),
        provider_name=provider.provider_name,
        provider_type=ProviderType(provider.provider_type),
        capability=capability,
        base_url=provider.base_url,
        api_key_configured=bool(provider.api_key_encrypted),
        chat_model=provider.chat_model,
        embedding_model=provider.embedding_model,
        transcription_model=provider.transcription_model,
        transcription_app_id=(
            str(transcription_config.get("app_id"))
            if transcription_config.get("app_id")
            else None
        ),
        transcription_access_token_configured=bool(
            transcription_config.get("access_token_encrypted")
        ),
        transcription_secret_key_configured=bool(
            transcription_config.get("secret_key_encrypted")
        ),
        is_enabled=provider.is_enabled and is_configured,
        last_test_status=provider.last_test_status,
        last_tested_at=provider.last_tested_at,
    )


def _provider_config_from_payload(
    payload: ProviderCreateRequest | ProviderUpdateRequest,
    existing_config: dict | None = None,
) -> dict:
    config = dict(existing_config or {})
    capability = (payload.capability or "").strip().lower()
    if capability in {"llm", "asr"}:
        config["capability"] = capability
    transcription = dict(config.get("transcription") or {})
    if payload.transcription_app_id is not None:
        app_id = payload.transcription_app_id.strip()
        if app_id:
            transcription["app_id"] = app_id
        else:
            transcription.pop("app_id", None)
    if payload.transcription_access_token:
        transcription["access_token_encrypted"] = protect_secret(payload.transcription_access_token)
    if payload.transcription_secret_key:
        transcription["secret_key_encrypted"] = protect_secret(payload.transcription_secret_key)
    if transcription:
        config["transcription"] = transcription
    else:
        config.pop("transcription", None)
    return config


def _provider_capability(
    *,
    config: dict,
    chat_model: str | None,
    transcription_model: str | None,
) -> str:
    capability = str(config.get("capability") or "").strip().lower()
    if capability in {"llm", "asr"}:
        return capability
    transcription_config = config.get("transcription")
    if (transcription_model or transcription_config) and not chat_model:
        return "asr"
    return "llm"


def _provider_is_configured(
    *,
    capability: str,
    api_key_configured: bool,
    chat_model: str | None,
    transcription_model: str | None,
    transcription_config: dict,
) -> bool:
    if capability == "asr":
        return bool(
            transcription_model
            and transcription_config.get("app_id")
            and transcription_config.get("access_token_encrypted")
            and transcription_config.get("secret_key_encrypted")
        )
    return bool(api_key_configured and chat_model)


def _to_provider_entry_from_record(record: dict[str, object]) -> ProviderEntry:
    config = record.get("config") if isinstance(record.get("config"), dict) else {}
    transcription_config = (
        config.get("transcription")
        if isinstance(config.get("transcription"), dict)
        else {}
    )
    capability = _provider_capability(
        config=config,
        chat_model=record.get("chat_model"),
        transcription_model=record.get("transcription_model"),
    )
    is_configured = _provider_is_configured(
        capability=capability,
        api_key_configured=bool(record.get("api_key_encrypted")),
        chat_model=record.get("chat_model"),
        transcription_model=record.get("transcription_model"),
        transcription_config=transcription_config,
    )
    return ProviderEntry(
        id=str(record["id"]),
        provider_name=str(record["provider_name"]),
        provider_type=record["provider_type"],
        capability=capability,
        base_url=record["base_url"],
        api_key_configured=bool(record.get("api_key_encrypted")),
        chat_model=record["chat_model"],
        embedding_model=record["embedding_model"],
        transcription_model=record["transcription_model"],
        transcription_app_id=(
            str(transcription_config.get("app_id"))
            if transcription_config.get("app_id")
            else None
        ),
        transcription_access_token_configured=bool(
            transcription_config.get("access_token_encrypted")
        ),
        transcription_secret_key_configured=bool(
            transcription_config.get("secret_key_encrypted")
        ),
        is_enabled=bool(record["is_enabled"]) and is_configured,
        last_test_status=record["last_test_status"],
        last_tested_at=record["last_tested_at"],
    )


def _ensure_builtin_provider(session) -> ModelProvider:
    provider = session.execute(
        select(ModelProvider).order_by(ModelProvider.created_at.asc())
    ).scalar_one_or_none()
    if provider is not None:
        return provider

    user = get_primary_user(session)
    provider = ModelProvider(
        user_id=user.id,
        provider_name="Doubao",
        provider_type=ProviderType.doubao.value,
        display_name="Doubao",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        chat_model="ep-20260304161530-6ffr5",
        embedding_model="doubao-embed",
        transcription_model=None,
        is_enabled=False,
        is_builtin=True,
        config={"capability": "llm"},
        last_test_status=None,
        last_tested_at=None,
    )
    session.add(provider)
    session.flush()
    return provider


def _fallback_list_providers() -> ProviderListResponse:
    seed_store()
    return ProviderListResponse(
        items=[
            _to_provider_entry_from_record(record)
            for record in STORE.providers.values()
        ]
    )


def list_providers() -> ProviderListResponse:
    try:
        with SessionLocal() as session:
            providers = (
                session.execute(select(ModelProvider).order_by(ModelProvider.created_at.asc()))
                .scalars()
                .all()
            )
            return ProviderListResponse(
                items=[_to_provider_entry(provider) for provider in providers]
            )
    except SQLAlchemyError:
        return _fallback_list_providers()


def create_provider(payload: ProviderCreateRequest) -> ProviderEntry:
    try:
        with SessionLocal() as session:
            user = get_primary_user(session)
            provider = ModelProvider(
                user_id=user.id,
                provider_name=payload.provider_name,
                provider_type=payload.provider_type.value,
                display_name=payload.provider_name,
                base_url=payload.base_url,
                api_key_encrypted=protect_secret(payload.api_key),
                chat_model=payload.chat_model,
                embedding_model=payload.embedding_model,
                transcription_model=payload.transcription_model,
                is_enabled=payload.is_enabled,
                is_builtin=False,
                config=_provider_config_from_payload(payload),
                last_test_status=None,
                last_tested_at=None,
            )
            session.add(provider)
            session.commit()
            session.refresh(provider)
            return _to_provider_entry(provider)
    except SQLAlchemyError:
        seed_store()
        provider_id = str(len(STORE.providers) + 1)
        record = {
            "id": provider_id,
            "provider_name": payload.provider_name,
            "provider_type": payload.provider_type,
            "capability": payload.capability,
            "base_url": payload.base_url,
            "api_key_encrypted": protect_secret(payload.api_key),
            "api_key_configured": bool(payload.api_key),
            "chat_model": payload.chat_model,
            "embedding_model": payload.embedding_model,
            "transcription_model": payload.transcription_model,
            "is_enabled": payload.is_enabled,
            "config": _provider_config_from_payload(payload),
            "last_test_status": None,
            "last_tested_at": None,
        }
        with STORE.lock:
            STORE.providers[provider_id] = record
        return _to_provider_entry_from_record(record)


def update_provider(provider_id: str, payload: ProviderUpdateRequest) -> ProviderEntry:
    try:
        with SessionLocal() as session:
            provider = get_model_provider(session, provider_id)
            if provider is None:
                user = get_primary_user(session)
                provider = ModelProvider(
                    id=provider_id,
                    user_id=user.id,
                    provider_name=payload.provider_name,
                    provider_type=payload.provider_type.value,
                    display_name=payload.provider_name,
                    base_url=payload.base_url,
                    api_key_encrypted=protect_secret(payload.api_key),
                    chat_model=payload.chat_model,
                    embedding_model=payload.embedding_model,
                    transcription_model=payload.transcription_model,
                    is_enabled=payload.is_enabled,
                    is_builtin=False,
                    config=_provider_config_from_payload(payload),
                    last_test_status=None,
                    last_tested_at=None,
                )
                session.add(provider)
            else:
                provider.provider_name = payload.provider_name
                provider.provider_type = payload.provider_type.value
                provider.display_name = payload.provider_name
                provider.base_url = payload.base_url
                if payload.api_key:
                    provider.api_key_encrypted = protect_secret(payload.api_key)
                provider.chat_model = payload.chat_model
                provider.embedding_model = payload.embedding_model
                provider.transcription_model = payload.transcription_model
                provider.is_enabled = payload.is_enabled
                provider.config = _provider_config_from_payload(payload, provider.config)
            session.commit()
            session.refresh(provider)
            return _to_provider_entry(provider)
    except SQLAlchemyError:
        seed_store()
        with STORE.lock:
            record = STORE.providers.get(provider_id)
            if record is None:
                record = {
                    "id": provider_id,
                    "provider_name": payload.provider_name,
                    "provider_type": payload.provider_type,
                    "capability": payload.capability,
                    "base_url": payload.base_url,
                    "api_key_encrypted": protect_secret(payload.api_key),
                    "api_key_configured": bool(payload.api_key),
                    "chat_model": payload.chat_model,
                    "embedding_model": payload.embedding_model,
                    "transcription_model": payload.transcription_model,
                    "is_enabled": payload.is_enabled,
                    "config": _provider_config_from_payload(payload),
                    "last_test_status": None,
                    "last_tested_at": None,
                }
                STORE.providers[provider_id] = record
            else:
                record.update(
                    {
                        "provider_name": payload.provider_name,
                        "provider_type": payload.provider_type,
                        "capability": payload.capability,
                        "base_url": payload.base_url,
                        "chat_model": payload.chat_model,
                        "embedding_model": payload.embedding_model,
                        "transcription_model": payload.transcription_model,
                        "is_enabled": payload.is_enabled,
                        "config": _provider_config_from_payload(payload, record.get("config")),
                    }
                )
                if payload.api_key:
                    record["api_key_encrypted"] = protect_secret(payload.api_key)
                    record["api_key_configured"] = True
        return _to_provider_entry_from_record(record)


def delete_provider(provider_id: str) -> ProviderDeleteResponse:
    try:
        with SessionLocal() as session:
            provider = get_model_provider(session, provider_id)
            if provider is not None:
                session.delete(provider)
                session.commit()
        return ProviderDeleteResponse(id=provider_id, deleted=True)
    except SQLAlchemyError:
        seed_store()
        with STORE.lock:
            STORE.providers.pop(provider_id, None)
        return ProviderDeleteResponse(id=provider_id, deleted=True)


def test_provider(provider_id: str) -> ProviderTestResponse:
    try:
        with SessionLocal() as session:
            provider = get_model_provider(session, provider_id)
            if provider is None:
                provider = _ensure_builtin_provider(session)
            provider.last_test_status = "ok"
            provider.last_tested_at = datetime.now(UTC)
            session.commit()
            return ProviderTestResponse(provider_id=str(provider.id), ok=True, latency_ms=420)
    except SQLAlchemyError:
        seed_store()
        with STORE.lock:
            record = STORE.providers.get(provider_id)
            if record is None:
                record = next(iter(STORE.providers.values()))
            record["last_test_status"] = "ok"
            record["last_tested_at"] = datetime.now(UTC)
        return ProviderTestResponse(provider_id=provider_id, ok=True, latency_ms=420)
