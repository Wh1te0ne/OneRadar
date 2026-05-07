from fastapi import APIRouter, HTTPException, Response

from app.schemas.common import ReadingState
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
    BilibiliPreviewRequest,
    BilibiliPreviewResponse,
    ImportItemRequest,
    ImportItemResponse,
    ItemDeleteResponse,
    ItemDetailResponse,
    ItemListResponse,
    ItemReprocessRequest,
    ItemReprocessResponse,
    ReadingStateUpdateRequest,
)
from app.services.folders_service import create_folder as create_folder_service
from app.services.folders_service import delete_folder as delete_folder_service
from app.services.folders_service import list_folders as list_folders_service
from app.services.folders_service import move_item_to_folder as move_item_to_folder_service
from app.services.folders_service import update_folder as update_folder_service
from app.services.items_service import delete_item as delete_item_service
from app.services.items_service import fetch_bilibili_cover as fetch_bilibili_cover_service
from app.services.items_service import generate_item_summary as generate_item_summary_service
from app.services.items_service import get_item as get_item_service
from app.services.items_service import import_item as import_item_service
from app.services.items_service import list_deleted_items as list_deleted_items_service
from app.services.items_service import list_items as list_items_service
from app.services.items_service import purge_item as purge_item_service
from app.services.items_service import preview_bilibili_item as preview_bilibili_item_service
from app.services.items_service import restore_item as restore_item_service
from app.services.items_service import reprocess_item as reprocess_item_service
from app.services.items_service import update_reading_state as update_reading_state_service

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
    return import_item_service(
        payload.url,
        payload.source_hint,
        title=payload.title,
        site_title=payload.site_title,
        author=payload.author,
        published_at=payload.published_at,
        summary=payload.summary,
        parsed_text=payload.parsed_text,
        parser_name=payload.parser_name,
        parser_version=payload.parser_version,
        generate_summary=payload.generate_summary,
        allow_duplicate=payload.allow_duplicate,
    )


@router.post("/bilibili/preview")
def preview_bilibili_item(payload: BilibiliPreviewRequest) -> BilibiliPreviewResponse:
    try:
        return preview_bilibili_item_service(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/bilibili/cover")
def bilibili_cover(url: str) -> Response:
    try:
        content, media_type = fetch_bilibili_cover_service(url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("")
def list_items(
    page: int = 1,
    page_size: int = 20,
    keyword: str | None = None,
    source_type: str | None = None,
    status: str | None = None,
    tag: str | None = None,
    folder_id: str | None = None,
    collection_id: str | None = None,
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
        collection_id=collection_id,
        inbox_only=inbox_only,
    )


@router.get("/trash")
def list_deleted_items(page: int = 1, page_size: int = 100) -> ItemListResponse:
    return list_deleted_items_service(page, page_size)


@router.post("/trash/{item_id}/restore")
def restore_item(item_id: str) -> ItemDeleteResponse:
    try:
        return restore_item_service(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/trash/{item_id}/purge")
def purge_item(item_id: str) -> ItemDeleteResponse:
    try:
        return purge_item_service(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{item_id}")
def get_item(item_id: str) -> ItemDetailResponse:
    try:
        return get_item_service(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{item_id}/reading-state")
def update_reading_state(item_id: str, payload: ReadingStateUpdateRequest) -> ReadingState:
    try:
        return update_reading_state_service(item_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{item_id}/reprocess")
def reprocess_item(
    item_id: str,
    payload: ItemReprocessRequest | None = None,
) -> ItemReprocessResponse:
    _ = payload
    return reprocess_item_service(item_id)


@router.post("/{item_id}/summaries/generate")
def generate_item_summary(item_id: str) -> ItemReprocessResponse:
    try:
        return generate_item_summary_service(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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

