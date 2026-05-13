from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class IntegrationTokenCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    scopes: list[str] = Field(default_factory=lambda: ["mcp:read"])


class IntegrationTokenEntry(BaseModel):
    id: str
    name: str
    token_prefix: str
    scopes: list[str]
    created_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


class IntegrationTokenCreateResponse(BaseModel):
    item: IntegrationTokenEntry
    token: str


class IntegrationTokenListResponse(BaseModel):
    items: list[IntegrationTokenEntry]


class IntegrationTokenRevokeResponse(BaseModel):
    id: str
    revoked: bool
