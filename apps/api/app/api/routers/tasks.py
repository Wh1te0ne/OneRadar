from fastapi import APIRouter

from app.schemas.tasks import TaskEntry, TaskListResponse, TaskRetryResponse
from app.services.tasks_service import get_task as get_task_service
from app.services.tasks_service import list_tasks as list_tasks_service
from app.services.tasks_service import retry_task as retry_task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("")
def list_tasks(page: int = 1, page_size: int = 20) -> TaskListResponse:
    return list_tasks_service(page, page_size)


@router.get("/{task_id}")
def get_task(task_id: str) -> TaskEntry:
    return get_task_service(task_id)


@router.post("/{task_id}/retry")
def retry_task(task_id: str) -> TaskRetryResponse:
    return retry_task_service(task_id)
