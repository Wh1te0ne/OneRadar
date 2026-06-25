from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class FeedPreviewItem(BaseModel):
    id: str
    title: str
    translated_title: str | None = None
    display_title: str | None = None
    link: str
    summary: str | None = None
    translated_summary: str | None = None
    display_summary: str | None = None
    translation_status: str | None = None
    translation_provider: str | None = None
    translation_model: str | None = None
    translated_at: datetime | None = None
    author: str | None = None
    published_at: datetime | None = None
    tags: list[str] = Field(default_factory=list)
    is_saved: bool = False
    saved_item_id: str | None = None
    saved_uid: str | None = None


class FeedPreviewResponse(BaseModel):
    source_url: str
    site_title: str
    site_url: str | None = None
    description: str | None = None
    items: list[FeedPreviewItem]
    fetched_at: datetime


class FeedArticlePreviewResponse(BaseModel):
    source_url: str
    final_url: str | None = None
    title: str
    site_title: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    summary: str | None = None
    plain_text: str
    parser_name: str = "feed-preview"
    parser_version: str = "v1"
    fetched_at: datetime
    is_saved: bool = False
    saved_item_id: str | None = None
    saved_uid: str | None = None
    can_generate_ai: bool = False


class FeedSourceEntry(BaseModel):
    source_url: str
    site_title: str
    site_url: str | None = None
    description: str | None = None
    last_loaded_at: datetime
    last_refresh_status: str | None = None
    last_refresh_error: str | None = None
    last_refreshed_at: datetime | None = None
    entry_count: int = 0
    today_count: int = 0
    week_count: int = 0


class FeedStateResponse(BaseModel):
    sources: list[FeedSourceEntry] = Field(default_factory=list)
    feeds: dict[str, FeedPreviewResponse] = Field(default_factory=dict)
    read_entries: list[str] = Field(default_factory=list)
    window: str = "all"


class FeedRefreshResponse(BaseModel):
    total: int
    refreshed: int
    failed: int
    errors: dict[str, str] = Field(default_factory=dict)


class FeedCacheRequest(BaseModel):
    feed: FeedPreviewResponse


class FeedReadRequest(BaseModel):
    entry_key: str = Field(min_length=1)


class FeedSourceErrorRequest(BaseModel):
    source_url: str = Field(min_length=1)
    site_title: str | None = None
    error_message: str = Field(min_length=1)


class FeedDeleteSourceResponse(BaseModel):
    source_url: str
    deleted: bool
