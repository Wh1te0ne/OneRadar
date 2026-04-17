from fastapi import APIRouter, HTTPException

from app.schemas.folders import (
    FolderCreateRequest,
    FolderDeleteResponse,
    FolderEntry,
    FolderListResponse,
    FolderUpdateRequest,
    MoveItemRequest,
    MoveItemResponse,
)
from app.schemas.items import (
    ImportItemRequest,
    ImportItemResponse,
    ItemDeleteResponse,
    ItemDetailResponse,
    ItemListResponse,
    ItemReprocessRequest,
    ItemReprocessResponse,
)
from app.services.folders_service import create_folder as create_folder_service
from app.services.folders_service import delete_folder as delete_folder_service
from app.services.folders_service import list_folders as list_folders_service
from app.services.folders_service import move_item_to_folder as move_item_to_folder_service
from app.services.folders_service import update_folder as update_folder_service
from app.services.items_service import delete_item as delete_item_service
from app.services.items_service import get_item as get_item_service
from app.services.items_service import import_item as import_item_service
from app.services.items_service import list_items as list_items_service
from app.services.items_service import reprocess_item as reprocess_item_service

router = APIRouter(prefix="/items", tags=["items"])


@router.get("/folders")
def list_folders() -> FolderListResponse:
    return list_folders_service()


@router.post("/folders")
def create_folder(payload: FolderCreateRequest) -> FolderEntry:
    return create_folder_service(payload)


@router.patch("/folders/{folder_id}")
def update_folder(folder_id: str, payload: FolderUpdateRequest) -> FolderEntry:
    try:
        return update_folder_service(folder_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/folders/{folder_id}")
def delete_folder(folder_id: str) -> FolderDeleteResponse:
    return delete_folder_service(folder_id)


@router.post("/import")
def import_item(payload: ImportItemRequest) -> ImportItemResponse:
    return import_item_service(payload.url, payload.source_hint)


@router.get("")
def list_items(
    page: int = 1,
    page_size: int = 20,
    keyword: str | None = None,
    source_type: str | None = None,
    status: str | None = None,
    tag: str | None = None,
    folder_id: str | None = None,
    inbox_only: bool = False,
) -> ItemListResponse:
    return list_items_service(
        page,
        page_size,
        keyword=keyword,
        source_type=source_type,
        status=status,
        tag=tag,
        folder_id=folder_id,
        inbox_only=inbox_only,
    )


@router.get("/{item_id}")
def get_item(item_id: str) -> ItemDetailResponse:
    try:
        return get_item_service(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{item_id}/reprocess")
def reprocess_item(item_id: str, payload: ItemReprocessRequest | None = None) -> ItemReprocessResponse:
    _ = payload
    return reprocess_item_service(item_id)


@router.delete("/{item_id}")
def delete_item(item_id: str) -> ItemDeleteResponse:
    try:
        return delete_item_service(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{item_id}/move")
def move_item_to_folder(item_id: str, payload: MoveItemRequest) -> MoveItemResponse:
    try:
        return move_item_to_folder_service(item_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

