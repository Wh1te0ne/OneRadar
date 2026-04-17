from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class BilibiliIntegrationSettingsEntry(BaseModel):
    integration_key: str = "bilibili"
    display_name: str = "Bilibili"
    is_enabled: bool = False
    has_cookie_values: bool = False
    ready_for_authenticated_fetch: bool = False
    sessdata_configured: bool = False
    sessdata_preview: str | None = None
    bili_jct_configured: bool = False
    bili_jct_preview: str | None = None
    buvid3_configured: bool = False
    buvid3_preview: str | None = None
    updated_at: datetime | None = None


class BilibiliIntegrationSettingsUpdateRequest(BaseModel):
    is_enabled: bool = True
    cookie_header: str | None = None
    sessdata: str | None = Field(default=None)
    bili_jct: str | None = Field(default=None)
    buvid3: str | None = Field(default=None)


class IntegrationSecretStatus(BaseModel):
    configured: bool
    preview: str | None = None


class BilibiliIntegrationCookieParseResponse(BaseModel):
    extracted: dict[str, IntegrationSecretStatus]
    extracted_count: int
