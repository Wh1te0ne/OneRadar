from __future__ import annotations

import json
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

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
from app.services.credential_crypto import protect_secret, reveal_secret
from app.services.db_access import get_model_provider, get_primary_user
from app.services.store import STORE, seed_store

SUPPORTED_INPUT_CAPABILITIES = ("text", "image", "audio", "video")


def list_presets() -> list[ProviderPresetEntry]:
    return [
        ProviderPresetEntry(provider_type=ProviderType.doubao, provider_name="Doubao"),
        ProviderPresetEntry(provider_type=ProviderType.deepseek, provider_name="DeepSeek"),
        ProviderPresetEntry(
            provider_type=ProviderType.openai_compatible,
            provider_name="OpenAI Compatible",
        ),
    ]


def _to_provider_entry(provider: ModelProvider) -> ProviderEntry:
    config = dict(provider.config or {})
    transcription_config = dict(config.get("transcription") or {})
    llm_config = dict(config.get("llm") or {})
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
        input_capabilities=_provider_input_capabilities(config, capability),
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
        thinking_mode=_normalize_thinking_mode(llm_config.get("thinking_mode")),
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
    else:
        capability = str(config.get("capability") or "llm").strip().lower()
        if capability not in {"llm", "asr"}:
            capability = "llm"
    if payload.input_capabilities is not None:
        config["input_capabilities"] = _normalize_input_capabilities(
            payload.input_capabilities,
            capability,
        )
    llm = dict(config.get("llm") or {})
    if payload.thinking_mode is not None:
        thinking_mode = _normalize_thinking_mode(payload.thinking_mode)
        if thinking_mode == "default":
            llm.pop("thinking_mode", None)
        else:
            llm["thinking_mode"] = thinking_mode
    if llm:
        config["llm"] = llm
    else:
        config.pop("llm", None)
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


def _default_input_capabilities(capability: str) -> list[str]:
    if capability == "asr":
        return ["audio"]
    return ["text"]


def _normalize_input_capabilities(value: object, capability: str) -> list[str]:
    if not isinstance(value, list):
        return _default_input_capabilities(capability)
    normalized = {
        str(item or "").strip().lower()
        for item in value
        if str(item or "").strip().lower() in SUPPORTED_INPUT_CAPABILITIES
    }
    return [capability_name for capability_name in SUPPORTED_INPUT_CAPABILITIES if capability_name in normalized] or _default_input_capabilities(capability)


def _provider_input_capabilities(config: dict, capability: str) -> list[str]:
    return _normalize_input_capabilities(config.get("input_capabilities"), capability)


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


def _validate_provider_payload(
    payload: ProviderCreateRequest | ProviderUpdateRequest,
    *,
    existing_provider: ModelProvider | None = None,
    existing_record: dict[str, object] | None = None,
) -> None:
    config = _provider_config_from_payload(
        payload,
        existing_provider.config if existing_provider is not None else (
            existing_record.get("config") if existing_record else None
        ),
    )
    capability = _provider_capability(
        config=config,
        chat_model=payload.chat_model,
        transcription_model=payload.transcription_model,
    )
    if capability == "asr":
        transcription = dict(config.get("transcription") or {})
        has_access_token = bool(
            payload.transcription_access_token
            or transcription.get("access_token_encrypted")
        )
        has_secret_key = bool(
            payload.transcription_secret_key
            or transcription.get("secret_key_encrypted")
        )
        if not payload.transcription_app_id:
            raise ValueError("ASR 模型需要填写 APP ID")
        if not payload.transcription_model:
            raise ValueError("ASR 模型需要填写资源 ID")
        if not has_access_token:
            raise ValueError("ASR 模型需要填写 Access Token")
        if not has_secret_key:
            raise ValueError("ASR 模型需要填写 Secret Key")
        return

    has_api_key = bool(
        payload.api_key
        or (existing_provider.api_key_encrypted if existing_provider is not None else None)
        or (existing_record.get("api_key_encrypted") if existing_record else None)
    )
    if not payload.base_url:
        raise ValueError("大语言模型需要填写 BaseURL")
    if not payload.chat_model:
        raise ValueError("大语言模型需要填写模型名或 Endpoint")
    if not has_api_key:
        raise ValueError("大语言模型需要填写 API Key")


def _disable_other_enabled_providers(
    session,
    *,
    user_id,
    provider_id: str | None,
    capability: str,
) -> None:
    providers = session.execute(
        select(ModelProvider).where(ModelProvider.user_id == user_id)
    ).scalars().all()
    for candidate in providers:
        if provider_id and str(candidate.id) == provider_id:
            continue
        candidate_capability = _provider_capability(
            config=dict(candidate.config or {}),
            chat_model=candidate.chat_model,
            transcription_model=candidate.transcription_model,
        )
        if candidate_capability == capability:
            candidate.is_enabled = False


def _disable_other_enabled_records(provider_id: str, capability: str) -> None:
    for candidate_id, candidate in STORE.providers.items():
        if candidate_id == provider_id:
            continue
        candidate_capability = _provider_capability(
            config=candidate.get("config") if isinstance(candidate.get("config"), dict) else {},
            chat_model=candidate.get("chat_model"),
            transcription_model=candidate.get("transcription_model"),
        )
        if candidate_capability == capability:
            candidate["is_enabled"] = False


def _to_provider_entry_from_record(record: dict[str, object]) -> ProviderEntry:
    config = record.get("config") if isinstance(record.get("config"), dict) else {}
    llm_config = config.get("llm") if isinstance(config.get("llm"), dict) else {}
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
        input_capabilities=_provider_input_capabilities(config, capability),
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
        thinking_mode=_normalize_thinking_mode(llm_config.get("thinking_mode")),
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
        config={"capability": "llm", "input_capabilities": ["text"]},
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
    _validate_provider_payload(payload)
    try:
        with SessionLocal() as session:
            user = get_primary_user(session)
            capability = _provider_capability(
                config=_provider_config_from_payload(payload),
                chat_model=payload.chat_model,
                transcription_model=payload.transcription_model,
            )
            if payload.is_enabled:
                _disable_other_enabled_providers(
                    session,
                    user_id=user.id,
                    provider_id=None,
                    capability=capability,
                )
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
            if payload.is_enabled:
                _disable_other_enabled_records(
                    provider_id,
                    str(record["config"].get("capability") or "llm"),
                )
            STORE.providers[provider_id] = record
        return _to_provider_entry_from_record(record)


def update_provider(provider_id: str, payload: ProviderUpdateRequest) -> ProviderEntry:
    try:
        with SessionLocal() as session:
            provider = get_model_provider(session, provider_id)
            _validate_provider_payload(payload, existing_provider=provider)
            capability = _provider_capability(
                config=_provider_config_from_payload(
                    payload,
                    provider.config if provider else None,
                ),
                chat_model=payload.chat_model,
                transcription_model=payload.transcription_model,
            )
            if provider is None:
                user = get_primary_user(session)
                if payload.is_enabled:
                    _disable_other_enabled_providers(
                        session,
                        user_id=user.id,
                        provider_id=provider_id,
                        capability=capability,
                    )
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
                if payload.is_enabled:
                    _disable_other_enabled_providers(
                        session,
                        user_id=provider.user_id,
                        provider_id=provider_id,
                        capability=capability,
                    )
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
            _validate_provider_payload(payload, existing_record=record)
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
            capability = _provider_capability(
                config=record.get("config") if isinstance(record.get("config"), dict) else {},
                chat_model=record.get("chat_model"),
                transcription_model=record.get("transcription_model"),
            )
            if bool(record.get("is_enabled")):
                _disable_other_enabled_records(provider_id, capability)
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
            ok, latency_ms, message = _run_provider_test(
                provider_id=str(provider.id),
                provider_type=ProviderType(provider.provider_type),
                base_url=provider.base_url,
                api_key_encrypted=provider.api_key_encrypted,
                model_name=provider.chat_model,
                config=dict(provider.config or {}),
            )
            provider.last_test_status = "ok" if ok else "failed"
            provider.last_tested_at = datetime.now(UTC)
            session.commit()
            return ProviderTestResponse(
                provider_id=str(provider.id),
                ok=ok,
                latency_ms=latency_ms,
                message=message,
            )
    except SQLAlchemyError:
        seed_store()
        with STORE.lock:
            record = STORE.providers.get(provider_id)
            if record is None:
                record = next(iter(STORE.providers.values()))
            ok, latency_ms, message = _run_provider_test(
                provider_id=str(record["id"]),
                provider_type=ProviderType(record["provider_type"]),
                base_url=record.get("base_url"),
                api_key_encrypted=record.get("api_key_encrypted"),
                model_name=record.get("chat_model"),
                config=record.get("config") if isinstance(record.get("config"), dict) else {},
            )
            record["last_test_status"] = "ok" if ok else "failed"
            record["last_tested_at"] = datetime.now(UTC)
        return ProviderTestResponse(provider_id=provider_id, ok=ok, latency_ms=latency_ms, message=message)


def _normalize_thinking_mode(value: object) -> str:
    mode = str(value or "default").strip().lower()
    if mode == "auto":
        return "enabled"
    if mode in {"default", "enabled", "disabled"}:
        return mode
    return "default"


def _provider_thinking_mode(config: dict[str, Any]) -> str:
    llm_config = dict(config.get("llm") or {})
    return _normalize_thinking_mode(llm_config.get("thinking_mode"))


def _chat_endpoint(base_url: str | None) -> str:
    normalized = (base_url or "").strip().rstrip("/")
    if not normalized:
        raise ValueError("大语言模型 BaseURL 未配置")
    if normalized.endswith("/chat/completions"):
        return normalized
    return urljoin(f"{normalized}/", "chat/completions")


def _apply_thinking_payload(
    payload: dict[str, Any],
    *,
    provider_type: ProviderType,
    config: dict[str, Any],
) -> None:
    mode = _provider_thinking_mode(config)
    if mode == "default":
        return
    if provider_type == ProviderType.deepseek:
        payload["thinking"] = {"type": mode}
        if mode == "enabled":
            payload["reasoning_effort"] = "medium"
        payload.pop("temperature", None)
        return
    if provider_type == ProviderType.doubao:
        payload["thinking"] = {"type": mode}
        payload.pop("temperature", None)


def _run_provider_test(
    *,
    provider_id: str,
    provider_type: ProviderType,
    base_url: object,
    api_key_encrypted: object,
    model_name: object,
    config: dict[str, Any],
) -> tuple[bool, int, str]:
    api_key = str(reveal_secret(api_key_encrypted) or "").strip()
    model = str(model_name or "").strip()
    if not api_key:
        return False, 0, "API Key 未配置"
    if not model:
        return False, 0, "模型名未配置"
    try:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": "请只回复 OK。"}],
            "temperature": 0,
            "max_tokens": 64,
        }
        _apply_thinking_payload(payload, provider_type=provider_type, config=config)
        start = perf_counter()
        request = Request(
            _chat_endpoint(str(base_url or "")),
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urlopen(request, timeout=45) as response:
            response_payload = json.loads(response.read().decode("utf-8", errors="replace"))
        latency_ms = int((perf_counter() - start) * 1000)
        if not _extract_chat_text(response_payload):
            return False, latency_ms, "模型返回为空"
        return True, latency_ms, "模型连通性测试通过"
    except HTTPError as error:
        return False, 0, f"HTTP {error.code}: {error.reason}"
    except (URLError, TimeoutError, json.JSONDecodeError, ValueError) as error:
        return False, 0, str(error)


def _extract_chat_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [str(part.get("text") or "").strip() for part in content if isinstance(part, dict)]
        return "\n".join(part for part in parts if part).strip()
    return ""
