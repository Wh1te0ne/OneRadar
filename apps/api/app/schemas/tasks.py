from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import TaskStatus


class TaskEntry(BaseModel):
    id: str
    item_id: str
    task_type: str
    status: TaskStatus
    attempt_count: int
    error_message: str | None = None
    stage_label: str = "正在处理"
    stage_detail: str | None = None
    progress_percent: int = Field(default=0, ge=0, le=100)
    created_at: datetime


class TaskListResponse(BaseModel):
    items: list[TaskEntry]
    page: int
    page_size: int
    total: int


class TaskRetryResponse(BaseModel):
    task_id: str
    status: TaskStatus
