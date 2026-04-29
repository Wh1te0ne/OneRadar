from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class BilibiliIntegrationSettingsEntry(BaseModel):
    integration_key: str = "bilibili"
    display_name: str = "Bilibili"
    is_enabled: bool = False
    visual_enhancement_enabled: bool = False
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
    visual_enhancement_enabled: bool | None = None
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


class BilibiliQrcodeGenerateResponse(BaseModel):
    url: str
    qrcode_key: str
    expires_in_seconds: int = 180


class BilibiliQrcodePollRequest(BaseModel):
    qrcode_key: str = Field(min_length=1, max_length=128)


class BilibiliQrcodePollResponse(BaseModel):
    code: int
    state: str
    message: str
    saved_cookie: BilibiliIntegrationSettingsEntry | None = None
