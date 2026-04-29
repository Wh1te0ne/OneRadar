from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.annotations import HighlightEntry, NoteEntry
from app.schemas.common import ContentType, ItemStatus, ReadingState, SummaryType
from app.schemas.organization import CollectionEntry, TagEntry


class ImportItemRequest(BaseModel):
    url: str = Field(min_length=1)
    source_hint: str | None = None


class ImportItemResponse(BaseModel):
    uid: str
    item_id: str
    existing_uid: str | None = None
    task_id: str | None = None
    status: str
    content_type: ContentType
    folder_id: str = "inbox"
    folder_name: str = "稍后阅读"
    is_duplicate: bool = False


class ItemListEntry(BaseModel):
    uid: str
    id: str
    title: str
    content_type: ContentType
    source_url: str
    status: ItemStatus
    folder_id: str = "inbox"
    folder_name: str = "稍后阅读"
    is_inbox: bool = True
    is_read: bool
    is_favorited: bool
    progress_percent: float = Field(default=0, ge=0, le=100)
    last_read_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)


class ParsedDocument(BaseModel):
    plain_text: str
    structured_blocks: list[dict[str, object]]
    parser_name: str | None = None
    parser_version: str | None = None


class TranscriptSegment(BaseModel):
    start_ms: int
    end_ms: int
    text: str
    speaker: str | None = None


class Transcript(BaseModel):
    transcript_type: str
    language: str | None = None
    full_text: str
    segments: list[TranscriptSegment]
    provider_name: str | None = None
    model_name: str | None = None


class SummaryEntry(BaseModel):
    summary_type: SummaryType
    content: str
    model_name: str | None = None
    version: int = 1


class ItemDetailResponse(BaseModel):
    uid: str
    id: str
    title: str
    content_type: ContentType
    source_url: str
    status: ItemStatus
    folder_id: str = "inbox"
    folder_name: str = "稍后阅读"
    is_inbox: bool = True
    metadata: dict[str, object]
    parsed_document: ParsedDocument
    transcript: Transcript | None
    summaries: list[SummaryEntry]
    highlights: list[HighlightEntry]
    notes: list[NoteEntry]
    tags: list[TagEntry]
    collections: list[CollectionEntry]
    reading_state: ReadingState


class ReadingStateUpdateRequest(BaseModel):
    progress_percent: float | None = Field(default=None, ge=0, le=100)
    last_read_at: datetime | None = None
    is_archived: bool | None = None
    is_favorited: bool | None = None
    last_position_type: str | None = None
    last_position_value: str | None = None


class ItemReprocessRequest(BaseModel):
    steps: list[str] = Field(
        default_factory=lambda: ["extract", "transcribe", "summarize", "index"]
    )


class ItemReprocessResponse(BaseModel):
    item_id: str
    task_id: str
    status: str


class ItemDeleteResponse(BaseModel):
    uid: str
    deleted: bool


class ItemListResponse(BaseModel):
    items: list[ItemListEntry]
    page: int
    page_size: int
    total: int

