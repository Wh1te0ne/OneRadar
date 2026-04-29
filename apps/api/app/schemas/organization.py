from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TagEntry(BaseModel):
    id: str
    name: str


class TagSetRequest(BaseModel):
    tags: list[str] = Field(default_factory=list)


class TagListResponse(BaseModel):
    items: list[TagEntry]


class CollectionCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None


class CollectionEntry(BaseModel):
    id: str
    name: str
    description: str | None = None
    is_favorite: bool = False
    item_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CollectionListResponse(BaseModel):
    items: list[CollectionEntry]


class CollectionItemRequest(BaseModel):
    item_id: str
