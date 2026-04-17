from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class TaskType(str, Enum):
    FETCH_META = "fetch_meta"
    FETCH_HTML = "fetch_html"
    EXTRACT_ARTICLE = "extract_article"
    FETCH_SUBTITLES = "fetch_subtitles"
    EXTRACT_AUDIO = "extract_audio"
    TRANSCRIBE_AUDIO = "transcribe_audio"
    GENERATE_SUMMARY = "generate_summary"
    BUILD_INDEX = "build_index"
    REPROCESS_ITEM = "reprocess_item"
    SYNC_PROVIDER_TEST = "sync_provider_test"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    RETRYING = "retrying"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELED = "canceled"


@dataclass(slots=True)
class TaskEnvelope:
    task_id: UUID = field(default_factory=uuid4)
    item_id: UUID | None = None
    task_type: TaskType = TaskType.FETCH_META
    status: TaskStatus = TaskStatus.PENDING
    payload: dict[str, Any] = field(default_factory=dict)
    attempt_count: int = 0
    max_attempts: int = 3


@dataclass(slots=True)
class TaskResult:
    status: TaskStatus
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)


def build_default_task_plan(task_type: TaskType) -> list[TaskType]:
    if task_type in {TaskType.FETCH_META, TaskType.FETCH_HTML, TaskType.EXTRACT_ARTICLE}:
        return [TaskType.FETCH_META, TaskType.FETCH_HTML, TaskType.EXTRACT_ARTICLE]
    if task_type in {TaskType.FETCH_SUBTITLES, TaskType.EXTRACT_AUDIO, TaskType.TRANSCRIBE_AUDIO}:
        return [
            TaskType.FETCH_META,
            TaskType.FETCH_SUBTITLES,
            TaskType.EXTRACT_AUDIO,
            TaskType.TRANSCRIBE_AUDIO,
        ]
    if task_type in {TaskType.GENERATE_SUMMARY, TaskType.BUILD_INDEX, TaskType.REPROCESS_ITEM}:
        return [TaskType.GENERATE_SUMMARY, TaskType.BUILD_INDEX]
    return [task_type]
