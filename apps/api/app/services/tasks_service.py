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


def _to_task_entry(record: ProcessingTask) -> TaskEntry:
    return TaskEntry(
        id=str(record.id),
        item_id=str(record.content_item_id),
        task_type=record.task_type,
        status=TaskStatus(record.status),
        attempt_count=record.attempt_count,
        error_message=record.error_message,
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
    return TaskEntry(
        id=str(record["id"]),
        item_id=str(record["item_id"]),
        task_type=str(record["task_type"]),
        status=record["status"],
        attempt_count=int(record["attempt_count"]),
        error_message=record["error_message"],
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
