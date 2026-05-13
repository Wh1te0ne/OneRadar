from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError

from app.schemas.common import ProviderType
from app.schemas.providers import ProviderCreateRequest, ProviderUpdateRequest
from app.services import providers_service
from app.services.provider_registry import ProviderCapability, resolve_provider_config
from app.services.store import STORE


def test_create_provider_protects_api_key_in_fallback_store(monkeypatch) -> None:
    def failing_session_local():
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(providers_service, "SessionLocal", failing_session_local)

    response = providers_service.create_provider(
        ProviderCreateRequest(
            provider_name="Local OpenAI",
            provider_type=ProviderType.openai_compatible,
            input_capabilities=["text", "image"],
            base_url="https://api.example.test/v1",
            api_key="sk-test-secret",
            chat_model="chat-model",
            embedding_model="embed-model",
            transcription_model="asr-model",
        )
    )

    stored = STORE.providers[response.id]
    assert response.api_key_configured is True
    assert "api_key" not in stored
    assert stored["api_key_encrypted"] != "sk-test-secret"
    assert "sk-test-secret" not in stored["api_key_encrypted"]


def test_provider_registry_resolves_models_by_capability(monkeypatch) -> None:
    def failing_session_local():
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(providers_service, "SessionLocal", failing_session_local)

    provider = providers_service.create_provider(
        ProviderCreateRequest(
            provider_name="Capability Provider",
            provider_type=ProviderType.openai_compatible,
            input_capabilities=["text", "image"],
            base_url="https://api.example.test/v1",
            api_key="sk-capability-secret",
            chat_model="chat-model",
            embedding_model="embed-model",
            transcription_model="asr-model",
        )
    )

    summarization = resolve_provider_config(provider.id, ProviderCapability.summarization)
    embedding = resolve_provider_config(provider.id, ProviderCapability.embedding)
    transcription = resolve_provider_config(provider.id, ProviderCapability.transcription)
    visual = resolve_provider_config(provider.id, ProviderCapability.video_visual_understanding)

    assert summarization.model_name == "chat-model"
    assert embedding.model_name == "embed-model"
    assert transcription.model_name == "asr-model"
    assert visual.model_name == "chat-model"
    assert summarization.api_key == "sk-capability-secret"
    assert embedding.api_key == "sk-capability-secret"
    assert transcription.api_key == "sk-capability-secret"
    assert visual.api_key == "sk-capability-secret"


def test_provider_registry_skips_asr_provider_for_default_summarization(monkeypatch) -> None:
    def failing_session_local():
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(providers_service, "SessionLocal", failing_session_local)

    providers_service.create_provider(
        ProviderCreateRequest(
            provider_name="Doubao ASR",
            provider_type=ProviderType.doubao,
            capability="asr",
            transcription_model="volc.bigasr.auc_turbo",
            transcription_app_id="app-id",
            transcription_access_token="access-token",
            transcription_secret_key="secret-key",
            is_enabled=True,
        )
    )
    providers_service.create_provider(
        ProviderCreateRequest(
            provider_name="Doubao LLM",
            provider_type=ProviderType.doubao,
            capability="llm",
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            api_key="sk-llm-secret",
            chat_model="ep-chat",
            is_enabled=True,
        )
    )

    summarization = resolve_provider_config(None, ProviderCapability.summarization)

    assert summarization.provider_name == "Doubao LLM"
    assert summarization.model_name == "ep-chat"
    assert summarization.api_key == "sk-llm-secret"


def test_provider_service_requires_complete_llm_configuration(monkeypatch) -> None:
    def failing_session_local():
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(providers_service, "SessionLocal", failing_session_local)

    try:
        providers_service.create_provider(
            ProviderCreateRequest(
                provider_name="Incomplete LLM",
                provider_type=ProviderType.deepseek,
                capability="llm",
                base_url="https://api.deepseek.com/v1",
                chat_model="deepseek-chat",
                is_enabled=True,
            )
        )
    except ValueError as error:
        assert "API Key" in str(error)
    else:
        raise AssertionError("incomplete LLM provider should be rejected")


def test_provider_service_enables_only_one_provider_per_capability(monkeypatch) -> None:
    def failing_session_local():
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(providers_service, "SessionLocal", failing_session_local)

    first = providers_service.create_provider(
        ProviderCreateRequest(
            provider_name="First LLM",
            provider_type=ProviderType.openai_compatible,
            capability="llm",
            base_url="https://api.first.test/v1",
            api_key="sk-first",
            chat_model="first-chat",
            is_enabled=True,
        )
    )
    second = providers_service.create_provider(
        ProviderCreateRequest(
            provider_name="Second LLM",
            provider_type=ProviderType.deepseek,
            capability="llm",
            base_url="https://api.deepseek.com/v1",
            api_key="sk-second",
            chat_model="deepseek-chat",
            is_enabled=True,
        )
    )

    providers = providers_service.list_providers().items
    first_after = next(provider for provider in providers if provider.id == first.id)
    second_after = next(provider for provider in providers if provider.id == second.id)
    assert first_after.is_enabled is False
    assert second_after.is_enabled is True


def test_provider_service_persists_llm_thinking_mode(monkeypatch) -> None:
    def failing_session_local():
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(providers_service, "SessionLocal", failing_session_local)

    provider = providers_service.create_provider(
        ProviderCreateRequest(
            provider_name="DeepSeek Thinking",
            provider_type=ProviderType.deepseek,
            capability="llm",
            base_url="https://api.deepseek.com/v1",
            api_key="sk-thinking",
            chat_model="deepseek-v4-pro",
            thinking_mode="enabled",
            is_enabled=True,
        )
    )

    stored = STORE.providers[provider.id]
    assert provider.thinking_mode == "enabled"
    assert stored["config"]["llm"]["thinking_mode"] == "enabled"


def test_provider_service_persists_model_input_capabilities(monkeypatch) -> None:
    def failing_session_local():
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(providers_service, "SessionLocal", failing_session_local)

    provider = providers_service.create_provider(
        ProviderCreateRequest(
            provider_name="Video Model",
            provider_type=ProviderType.openai_compatible,
            capability="llm",
            input_capabilities=["text", "audio", "video"],
            base_url="https://api.example.test/v1",
            api_key="sk-video",
            chat_model="video-chat",
            is_enabled=True,
        )
    )

    assert provider.input_capabilities == ["text", "audio", "video"]
    assert STORE.providers[provider.id]["config"]["input_capabilities"] == ["text", "audio", "video"]

    updated = providers_service.update_provider(
        provider.id,
        ProviderUpdateRequest(
            provider_name="Video Model",
            provider_type=ProviderType.openai_compatible,
            capability="llm",
            input_capabilities=["text"],
            base_url="https://api.example.test/v1",
            chat_model="video-chat",
            is_enabled=True,
        ),
    )

    assert updated.input_capabilities == ["text"]
    assert STORE.providers[provider.id]["config"]["input_capabilities"] == ["text"]


def test_provider_service_normalizes_legacy_auto_thinking_mode(monkeypatch) -> None:
    def failing_session_local():
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(providers_service, "SessionLocal", failing_session_local)

    provider = providers_service.create_provider(
        ProviderCreateRequest(
            provider_name="Doubao Thinking",
            provider_type=ProviderType.doubao,
            capability="llm",
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            api_key="sk-thinking",
            chat_model="ep-thinking",
            thinking_mode="auto",
            is_enabled=True,
        )
    )

    stored = STORE.providers[provider.id]
    assert provider.thinking_mode == "enabled"
    assert stored["config"]["llm"]["thinking_mode"] == "enabled"
