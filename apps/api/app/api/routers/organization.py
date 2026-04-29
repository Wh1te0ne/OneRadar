from fastapi import APIRouter, HTTPException

from app.schemas.organization import (
    CollectionCreateRequest,
    CollectionEntry,
    CollectionItemRequest,
    CollectionListResponse,
    TagListResponse,
    TagSetRequest,
)
from app.services.organization_service import (
    add_item_to_collection as add_item_to_collection_service,
)
from app.services.organization_service import create_collection as create_collection_service
from app.services.organization_service import get_collection as get_collection_service
from app.services.organization_service import list_collections as list_collections_service
from app.services.organization_service import list_item_tags as list_item_tags_service
from app.services.organization_service import (
    remove_item_from_collection as remove_item_from_collection_service,
)
from app.services.organization_service import set_item_tags as set_item_tags_service

router = APIRouter(tags=['organization'])


@router.post('/items/{item_id}/tags')
def set_item_tags(item_id: str, payload: TagSetRequest) -> TagListResponse:
    try:
        return set_item_tags_service(item_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get('/items/{item_id}/tags')
def list_item_tags(item_id: str) -> TagListResponse:
    try:
        return list_item_tags_service(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post('/collections')
def create_collection(payload: CollectionCreateRequest) -> CollectionEntry:
    try:
        return create_collection_service(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get('/collections')
def list_collections() -> CollectionListResponse:
    return list_collections_service()


@router.get('/collections/{collection_id}')
def get_collection(collection_id: str) -> CollectionEntry:
    try:
        return get_collection_service(collection_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post('/collections/{collection_id}/items')
def add_item_to_collection(collection_id: str, payload: CollectionItemRequest) -> CollectionEntry:
    try:
        return add_item_to_collection_service(collection_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete('/collections/{collection_id}/items/{item_id}')
def remove_item_from_collection(collection_id: str, item_id: str) -> CollectionEntry:
    try:
        return remove_item_from_collection_service(collection_id, item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
