from fastapi import APIRouter, HTTPException

from app.schemas.annotations import (
    HighlightCreateRequest,
    HighlightDeleteResponse,
    HighlightEntry,
    HighlightListResponse,
    NoteCreateRequest,
    NoteDeleteResponse,
    NoteEntry,
    NoteUpdateRequest,
)
from app.services.annotations_service import create_highlight as create_highlight_service
from app.services.annotations_service import create_note as create_note_service
from app.services.annotations_service import delete_highlight as delete_highlight_service
from app.services.annotations_service import delete_note as delete_note_service
from app.services.annotations_service import list_highlights as list_highlights_service
from app.services.annotations_service import update_note as update_note_service

router = APIRouter(tags=['annotations'])


@router.post('/items/{item_id}/highlights')
def create_highlight(item_id: str, payload: HighlightCreateRequest) -> HighlightEntry:
    try:
        return create_highlight_service(item_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get('/items/{item_id}/highlights')
def list_highlights(item_id: str) -> HighlightListResponse:
    try:
        return list_highlights_service(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete('/highlights/{highlight_id}')
def delete_highlight(highlight_id: str) -> HighlightDeleteResponse:
    try:
        return delete_highlight_service(highlight_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post('/items/{item_id}/notes')
def create_note(item_id: str, payload: NoteCreateRequest) -> NoteEntry:
    try:
        return create_note_service(item_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put('/notes/{note_id}')
def update_note(note_id: str, payload: NoteUpdateRequest) -> NoteEntry:
    try:
        return update_note_service(note_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete('/notes/{note_id}')
def delete_note(note_id: str) -> NoteDeleteResponse:
    try:
        return delete_note_service(note_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
