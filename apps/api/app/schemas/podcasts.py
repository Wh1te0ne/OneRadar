from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.items import ImportItemResponse


class PodcastSearchItem(BaseModel):
    itunes_id: str | None = None
    title: str
    author: str | None = None
    feed_url: str | None = None
    page_url: str | None = None
    image_url: str | None = None
    genre: str | None = None
    episode_count: int | None = None
    is_subscribable: bool = False


class PodcastSearchResponse(BaseModel):
    items: list[PodcastSearchItem]


class PodcastSubscriptionCreateRequest(BaseModel):
    feed_url: str = Field(min_length=1)
    title: str = Field(min_length=1)
    author: str | None = None
    image_url: str | None = None
    itunes_id: str | None = None
    page_url: str | None = None


class PodcastSubscriptionEntry(BaseModel):
    id: str
    feed_url: str
    title: str
    author: str | None = None
    image_url: str | None = None
    itunes_id: str | None = None
    page_url: str | None = None
    created_at: datetime
    updated_at: datetime


class PodcastSubscriptionListResponse(BaseModel):
    items: list[PodcastSubscriptionEntry]


class PodcastSubscriptionDeleteResponse(BaseModel):
    id: str
    deleted: bool


class PodcastEpisodeFeedEntry(BaseModel):
    id: str
    subscription_id: str | None = None
    feed_url: str
    podcast_title: str
    title: str
    guid: str | None = None
    link: str | None = None
    summary: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    duration_seconds: int | None = None
    enclosure_url: str
    enclosure_type: str | None = None
    enclosure_length: int | None = None
    image_url: str | None = None
    is_imported: bool = False
    item_id: str | None = None


class PodcastEpisodeFeedResponse(BaseModel):
    items: list[PodcastEpisodeFeedEntry]


class PodcastEpisodeImportRequest(BaseModel):
    feed_url: str = Field(min_length=1)
    podcast_title: str = Field(min_length=1)
    title: str = Field(min_length=1)
    guid: str | None = None
    link: str | None = None
    summary: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    duration_seconds: int | None = None
    enclosure_url: str = Field(min_length=1)
    enclosure_type: str | None = None
    enclosure_length: int | None = None
    image_url: str | None = None


class PodcastEpisodeImportResponse(ImportItemResponse):
    pass
