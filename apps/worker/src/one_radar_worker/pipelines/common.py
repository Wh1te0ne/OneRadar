from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from ..tasks import TaskType


@dataclass(slots=True)
class PipelineContext:
    item_id: UUID
    source_url: str
    task_type: TaskType
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PipelineStepResult:
    step_name: str
    ok: bool
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PipelineRunResult:
    ok: bool
    steps: list[PipelineStepResult] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PipelineQualityScore:
    value: float
    reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PipelineDocumentBlock:
    block_type: str
    text: str
    order: int
    data: dict[str, Any] = field(default_factory=dict)
