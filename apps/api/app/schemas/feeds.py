from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class FeedPreviewItem(BaseModel):
    id: str
    title: str
    link: str
    summary: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    tags: list[str] = Field(default_factory=list)


class FeedPreviewResponse(BaseModel):
    source_url: str
    site_title: str
    site_url: str | None = None
    description: str | None = None
    items: list[FeedPreviewItem]
    fetched_at: datetime
