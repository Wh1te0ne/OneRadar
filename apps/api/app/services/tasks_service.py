from __future__ import annotations

from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select

from app.db.models import ProcessingTask
from app.db.session import SessionLocal
from app.schemas.common import TaskStatus
from app.schemas.tasks import TaskEntry, TaskListResponse, TaskRetryResponse
from app.services.db_access import get_primary_user
from app.services.store import STORE, seed_store


def _task_stage(task_type: str, status: str) -> tuple[str, str | None, int]:
    status = str(getattr(status, "value", status))
    if task_type == "fetch_meta":
        mapping = {
            "pending": ("原文排队中", "等待获取元数据、原文和转写。", 10),
            "running": ("正在生成原文", "正在获取元数据、字幕/ASR 转写和可读正文。", 38),
            "retrying": ("原文处理中，等待重试", "上一次原文处理未完成，稍后会自动重试。", 28),
            "success": ("原文已生成", "原文和转写已经保存，等待 AI 摘要。", 100),
            "failed": ("原文生成失败", "原文或转写处理失败。", 100),
            "canceled": ("原文任务已取消", None, 100),
        }
        return mapping.get(status, ("正在生成原文", None, 38))
    if task_type == "generate_summary":
        mapping = {
            "pending": ("AI 摘要排队中", "原文已准备好，等待模型生成摘要。", 72),
            "running": ("AI 摘要生成中", "模型正在阅读原文并生成摘要。", 88),
            "retrying": ("AI 摘要等待重试", "上一次模型调用未完成，稍后会自动重试。", 82),
            "success": ("AI 摘要已完成", "摘要已经写入条目。", 100),
            "failed": ("AI 摘要失败", "模型摘要生成失败。", 100),
            "canceled": ("AI 摘要已取消", None, 100),
        }
        return mapping.get(status, ("AI 摘要处理中", None, 88))
    if task_type == "reprocess_item":
        mapping = {
            "pending": ("重新处理排队中", None, 12),
            "running": ("正在重新处理", None, 45),
            "retrying": ("重新处理等待重试", None, 35),
            "success": ("重新处理完成", None, 100),
            "failed": ("重新处理失败", None, 100),
            "canceled": ("重新处理已取消", None, 100),
        }
        return mapping.get(status, ("正在重新处理", None, 45))
    return ("正在处理", None, 50 if status in {"running", "retrying"} else 100 if status in {"success", "failed", "canceled"} else 10)


def _to_task_entry(record: ProcessingTask) -> TaskEntry:
    stage_label, stage_detail, progress_percent = _task_stage(record.task_type, record.status)
    return TaskEntry(
        id=str(record.id),
        item_id=str(record.content_item_id),
        task_type=record.task_type,
        status=TaskStatus(record.status),
        attempt_count=record.attempt_count,
        error_message=record.error_message,
        stage_label=stage_label,
        stage_detail=stage_detail,
        progress_percent=progress_percent,
        created_at=record.created_at,
    )


def _fallback_list_tasks(page: int, page_size: int) -> TaskListResponse:
    seed_store()
    tasks = sorted(STORE.tasks.values(), key=lambda record: record["created_at"], reverse=True)
    start = (page - 1) * page_size
    end = start + page_size
    return TaskListResponse(
        items=[
            TaskEntry(
                id=str(record["id"]),
                item_id=str(record["item_id"]),
                task_type=str(record["task_type"]),
                status=record["status"],
                attempt_count=int(record["attempt_count"]),
                error_message=record["error_message"],
                stage_label=_task_stage(str(record["task_type"]), str(record["status"]))[0],
                stage_detail=_task_stage(str(record["task_type"]), str(record["status"]))[1],
                progress_percent=_task_stage(str(record["task_type"]), str(record["status"]))[2],
                created_at=record["created_at"],
            )
            for record in tasks[start:end]
        ],
        page=page,
        page_size=page_size,
        total=len(tasks),
    )


def list_tasks(page: int, page_size: int) -> TaskListResponse:
    try:
        with SessionLocal() as session:
            tasks = session.execute(select(ProcessingTask).order_by(ProcessingTask.created_at.desc())).scalars().all()
            start = (page - 1) * page_size
            end = start + page_size
            return TaskListResponse(
                items=[_to_task_entry(record) for record in tasks[start:end]],
                page=page,
                page_size=page_size,
                total=len(tasks),
            )
    except SQLAlchemyError:
        return _fallback_list_tasks(page, page_size)


def get_task(task_id: str) -> TaskEntry:
    try:
        with SessionLocal() as session:
            task = session.get(ProcessingTask, UUID(task_id))
            if task is not None:
                return _to_task_entry(task)
    except (SQLAlchemyError, ValueError):
        pass

    seed_store()
    record = STORE.tasks.get(task_id)
    if record is None:
        record = next(iter(STORE.tasks.values()))
    stage_label, stage_detail, progress_percent = _task_stage(str(record["task_type"]), str(record["status"]))
    return TaskEntry(
        id=str(record["id"]),
        item_id=str(record["item_id"]),
        task_type=str(record["task_type"]),
        status=record["status"],
        attempt_count=int(record["attempt_count"]),
        error_message=record["error_message"],
        stage_label=stage_label,
        stage_detail=stage_detail,
        progress_percent=progress_percent,
        created_at=record["created_at"],
    )


def retry_task(task_id: str) -> TaskRetryResponse:
    try:
        with SessionLocal() as session:
            task = session.get(ProcessingTask, UUID(task_id))
            if task is not None:
                task.status = TaskStatus.retrying.value
                task.attempt_count = int(task.attempt_count) + 1
                session.commit()
                return TaskRetryResponse(task_id=str(task.id), status=TaskStatus.retrying)
    except (SQLAlchemyError, ValueError):
        pass

    seed_store()
    with STORE.lock:
        record = STORE.tasks.get(task_id)
        if record is None:
            record = next(iter(STORE.tasks.values()))
        record["status"] = TaskStatus.retrying
        record["attempt_count"] = int(record["attempt_count"]) + 1
    return TaskRetryResponse(task_id=task_id, status=TaskStatus.retrying)
