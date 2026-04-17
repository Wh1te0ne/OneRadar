from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ContentType(str, Enum):
    article = "article"
    bilibili_video = "bilibili_video"


class ItemStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    archived = "archived"


class TaskStatus(str, Enum):
    pending = "pending"
    running = "running"
    retrying = "retrying"
    success = "success"
    failed = "failed"
    canceled = "canceled"


class ProviderType(str, Enum):
    openai_compatible = "openai_compatible"
    doubao = "doubao"
    custom = "custom"


class ThemeMode(str, Enum):
    system = "system"
    light = "light"
    dark = "dark"


class SummaryType(str, Enum):
    one_line = "one_line"
    short = "short"
    outline = "outline"
    key_points = "key_points"


class TranscriptType(str, Enum):
    subtitle = "subtitle"
    asr = "asr"
    refined_asr = "refined_asr"


class ReadingState(BaseModel):
    progress_percent: float = Field(ge=0, le=100)
    last_read_at: datetime | None = None
    is_archived: bool = False
    is_favorited: bool = False
