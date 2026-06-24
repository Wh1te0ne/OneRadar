from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class UrlAnalysisRequest(BaseModel):
    url: str = Field(min_length=1)
    platform_hint: str | None = None


class UrlAnalysisResponse(BaseModel):
    source_url: str
    final_url: str | None = None
    platform: str
    content_type: str
    title: str
    source_name: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    original_text: str
    source_text_kind: str
    summary: str
    summary_provider: str = "extractive"
    model_name: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    fetched_at: datetime
    persisted: bool = False
