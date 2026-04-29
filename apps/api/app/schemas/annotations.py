from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class HighlightCreateRequest(BaseModel):
    quote_text: str = Field(min_length=1)
    anchor_type: str = "article_text"
    start_anchor: str | None = None
    end_anchor: str | None = None
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)
    segment_index: int | None = Field(default=None, ge=0)
    color: str | None = None


class HighlightEntry(BaseModel):
    id: str
    item_id: str
    quote_text: str
    anchor_type: str = "article_text"
    start_anchor: str | None = None
    end_anchor: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    segment_index: int | None = None
    color: str | None = None
    note_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class HighlightListResponse(BaseModel):
    items: list[HighlightEntry]


class HighlightDeleteResponse(BaseModel):
    id: str
    deleted: bool


class NoteCreateRequest(BaseModel):
    content: str = Field(min_length=1)
    highlight_id: str | None = None


class NoteUpdateRequest(BaseModel):
    content: str = Field(min_length=1)


class NoteEntry(BaseModel):
    id: str
    item_id: str
    content: str
    highlight_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class NoteDeleteResponse(BaseModel):
    id: str
    deleted: bool
