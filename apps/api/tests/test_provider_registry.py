from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError

from app.schemas.common import ProviderType
from app.schemas.providers import ProviderCreateRequest
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
