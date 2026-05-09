from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.annotations import HighlightEntry, NoteEntry
from app.schemas.common import ContentType, ItemStatus, ReadingState, SummaryType
from app.schemas.organization import CollectionEntry, TagEntry


class ImportItemRequest(BaseModel):
    url: str = Field(min_length=1)
    source_hint: str | None = None
    title: str | None = None
    site_title: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    summary: str | None = None
    parsed_text: str | None = None
    parser_name: str | None = None
    parser_version: str | None = None
    generate_summary: bool = False
    allow_duplicate: bool = False


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


class BilibiliPreviewRequest(BaseModel):
    url: str = Field(min_length=1)


class BilibiliPreviewResponse(BaseModel):
    content_type: ContentType = ContentType.bilibili_video
    source_url: str
    normalized_url: str
    title: str
    owner_name: str | None = None
    owner_id: int | None = None
    cover_url: str | None = None
    description: str | None = None
    duration_seconds: int | None = None
    duration_text: str | None = None
    published_at: datetime | None = None
    bvid: str | None = None
    aid: int | None = None
    cid: int | None = None
    page_count: int | None = None
    page_title: str | None = None
    subtitle_status: str = "确认加入后检测字幕"


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
    deleted_at: datetime | None = None
    delete_expires_at: datetime | None = None
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
    is_read: bool | None = None
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

