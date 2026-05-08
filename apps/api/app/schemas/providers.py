from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ProviderType


class ProviderPresetEntry(BaseModel):
    provider_type: ProviderType
    provider_name: str


class ProviderCreateRequest(BaseModel):
    provider_name: str = Field(min_length=1)
    provider_type: ProviderType
    capability: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    chat_model: str | None = None
    embedding_model: str | None = None
    transcription_model: str | None = None
    transcription_app_id: str | None = None
    transcription_access_token: str | None = None
    transcription_secret_key: str | None = None
    thinking_mode: str | None = None
    is_enabled: bool = True


class ProviderUpdateRequest(ProviderCreateRequest):
    pass


class ProviderDeleteResponse(BaseModel):
    id: str
    deleted: bool


class ProviderEntry(BaseModel):
    id: str
    provider_name: str
    provider_type: ProviderType
    capability: str = "llm"
    base_url: str | None = None
    api_key_configured: bool = False
    chat_model: str | None = None
    embedding_model: str | None = None
    transcription_model: str | None = None
    transcription_app_id: str | None = None
    transcription_access_token_configured: bool = False
    transcription_secret_key_configured: bool = False
    thinking_mode: str = "default"
    is_enabled: bool = True
    last_test_status: str | None = None
    last_tested_at: datetime | None = None


class ProviderListResponse(BaseModel):
    items: list[ProviderEntry]


class ProviderTestResponse(BaseModel):
    provider_id: str
    ok: bool
    latency_ms: int
    message: str | None = None
