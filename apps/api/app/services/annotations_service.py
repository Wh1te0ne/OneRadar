from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import ContentItem, Highlight, Note
from app.db.session import SessionLocal
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
from app.services.db_access import get_primary_user
from app.services.store import STORE, now_utc, seed_store


def _highlight_entry(record: Highlight) -> HighlightEntry:
    return HighlightEntry(
        id=str(record.id),
        item_id=str(record.content_item_id),
        quote_text=record.quote_text,
        anchor_type=record.anchor_type,
        start_anchor=record.start_anchor,
        end_anchor=record.end_anchor,
        start_offset=record.start_offset,
        end_offset=record.end_offset,
        segment_index=record.segment_index,
        color=record.color,
        note_id=str(record.note_id) if record.note_id else None,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _note_entry(record: Note) -> NoteEntry:
    return NoteEntry(
        id=str(record.id),
        item_id=str(record.content_item_id),
        content=record.content,
        highlight_id=str(record.highlight_id) if record.highlight_id else None,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _store_highlight_entry(record: dict[str, object]) -> HighlightEntry:
    return HighlightEntry.model_validate(record)


def _store_note_entry(record: dict[str, object]) -> NoteEntry:
    return NoteEntry.model_validate(record)


def _item_uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


def create_highlight(item_id: str, payload: HighlightCreateRequest) -> HighlightEntry:
    item_uuid = _item_uuid(item_id)
    if item_uuid is not None:
        try:
            with SessionLocal() as session:
                user = get_primary_user(session)
                item = session.execute(
                    select(ContentItem).where(
                        ContentItem.id == item_uuid,
                        ContentItem.user_id == user.id,
                    )
                ).scalar_one_or_none()
                if item is None:
                    raise ValueError('item not found')
                record = Highlight(
                    content_item_id=item.id,
                    user_id=user.id,
                    anchor_type=payload.anchor_type,
                    quote_text=payload.quote_text,
                    start_anchor=payload.start_anchor,
                    end_anchor=payload.end_anchor,
                    start_offset=payload.start_offset,
                    end_offset=payload.end_offset,
                    segment_index=payload.segment_index,
                    color=payload.color,
                    note_id=None,
                )
                session.add(record)
                session.commit()
                session.refresh(record)
                return _highlight_entry(record)
        except SQLAlchemyError:
            pass

    seed_store()
    with STORE.lock:
        item = STORE.items.get(item_id)
        if item is None:
            raise ValueError('item not found')
        now = now_utc()
        record = {
            'id': str(uuid4()),
            'item_id': item_id,
            'quote_text': payload.quote_text,
            'anchor_type': payload.anchor_type,
            'start_anchor': payload.start_anchor,
            'end_anchor': payload.end_anchor,
            'start_offset': payload.start_offset,
            'end_offset': payload.end_offset,
            'segment_index': payload.segment_index,
            'color': payload.color,
            'note_id': None,
            'created_at': now,
            'updated_at': now,
        }
        item.setdefault('highlights', []).append(record)
        item['updated_at'] = now
        return _store_highlight_entry(record)


def list_highlights(item_id: str) -> HighlightListResponse:
    item_uuid = _item_uuid(item_id)
    if item_uuid is not None:
        try:
            with SessionLocal() as session:
                user = get_primary_user(session)
                records = session.execute(
                    select(Highlight)
                    .where(Highlight.content_item_id == item_uuid, Highlight.user_id == user.id)
                    .order_by(Highlight.created_at.desc(), Highlight.id)
                ).scalars()
                return HighlightListResponse(items=[_highlight_entry(record) for record in records])
        except SQLAlchemyError:
            pass

    seed_store()
    item = STORE.items.get(item_id)
    if item is None:
        raise ValueError('item not found')
    return HighlightListResponse(
        items=[_store_highlight_entry(record) for record in item.get('highlights', [])]
    )


def delete_highlight(highlight_id: str) -> HighlightDeleteResponse:
    highlight_uuid = _item_uuid(highlight_id)
    if highlight_uuid is not None:
        try:
            with SessionLocal() as session:
                user = get_primary_user(session)
                record = session.execute(
                    select(Highlight).where(
                        Highlight.id == highlight_uuid,
                        Highlight.user_id == user.id,
                    )
                ).scalar_one_or_none()
                if record is None:
                    raise ValueError('highlight not found')
                bound_notes = session.execute(
                    select(Note).where(Note.highlight_id == record.id, Note.user_id == user.id)
                ).scalars()
                for note in bound_notes:
                    session.delete(note)
                session.delete(record)
                session.commit()
                return HighlightDeleteResponse(id=highlight_id, deleted=True)
        except SQLAlchemyError:
            pass

    seed_store()
    with STORE.lock:
        for item in STORE.items.values():
            highlights = list(item.get('highlights', []))
            target = next(
                (record for record in highlights if record.get('id') == highlight_id),
                None,
            )
            if target is None:
                continue
            bound_note_id = target.get('note_id')
            item['highlights'] = [
                record for record in highlights if record.get('id') != highlight_id
            ]
            item['notes'] = [
                record
                for record in item.get('notes', [])
                if record.get('highlight_id') != highlight_id and record.get('id') != bound_note_id
            ]
            item['updated_at'] = now_utc()
            return HighlightDeleteResponse(id=highlight_id, deleted=True)
    raise ValueError('highlight not found')


def create_note(item_id: str, payload: NoteCreateRequest) -> NoteEntry:
    item_uuid = _item_uuid(item_id)
    highlight_uuid = _item_uuid(payload.highlight_id) if payload.highlight_id else None
    if item_uuid is not None:
        try:
            with SessionLocal() as session:
                user = get_primary_user(session)
                item = session.execute(
                    select(ContentItem).where(
                        ContentItem.id == item_uuid,
                        ContentItem.user_id == user.id,
                    )
                ).scalar_one_or_none()
                if item is None:
                    raise ValueError('item not found')
                highlight = None
                if highlight_uuid is not None:
                    highlight = session.execute(
                        select(Highlight).where(
                            Highlight.id == highlight_uuid,
                            Highlight.content_item_id == item.id,
                            Highlight.user_id == user.id,
                        )
                    ).scalar_one_or_none()
                    if highlight is None:
                        raise ValueError('highlight not found')
                record = Note(
                    content_item_id=item.id,
                    user_id=user.id,
                    highlight_id=highlight.id if highlight else None,
                    content=payload.content,
                )
                session.add(record)
                session.flush()
                if highlight is not None:
                    highlight.note_id = record.id
                session.commit()
                session.refresh(record)
                return _note_entry(record)
        except SQLAlchemyError:
            pass

    seed_store()
    with STORE.lock:
        item = STORE.items.get(item_id)
        if item is None:
            raise ValueError('item not found')
        highlights = list(item.get('highlights', []))
        highlight = None
        if payload.highlight_id:
            highlight = next(
                (
                    candidate
                    for candidate in highlights
                    if candidate.get('id') == payload.highlight_id
                ),
                None,
            )
            if highlight is None:
                raise ValueError('highlight not found')
        now = now_utc()
        record = {
            'id': str(uuid4()),
            'item_id': item_id,
            'content': payload.content,
            'highlight_id': payload.highlight_id,
            'created_at': now,
            'updated_at': now,
        }
        item.setdefault('notes', []).append(record)
        if highlight is not None:
            highlight['note_id'] = record['id']
            highlight['updated_at'] = now
        item['updated_at'] = now
        return _store_note_entry(record)


def update_note(note_id: str, payload: NoteUpdateRequest) -> NoteEntry:
    note_uuid = _item_uuid(note_id)
    if note_uuid is not None:
        try:
            with SessionLocal() as session:
                user = get_primary_user(session)
                record = session.execute(
                    select(Note).where(Note.id == note_uuid, Note.user_id == user.id)
                ).scalar_one_or_none()
                if record is None:
                    raise ValueError('note not found')
                record.content = payload.content
                session.commit()
                session.refresh(record)
                return _note_entry(record)
        except SQLAlchemyError:
            pass

    seed_store()
    with STORE.lock:
        for item in STORE.items.values():
            for record in item.get('notes', []):
                if record.get('id') == note_id:
                    record['content'] = payload.content
                    record['updated_at'] = now_utc()
                    item['updated_at'] = record['updated_at']
                    return _store_note_entry(record)
    raise ValueError('note not found')


def delete_note(note_id: str) -> NoteDeleteResponse:
    note_uuid = _item_uuid(note_id)
    if note_uuid is not None:
        try:
            with SessionLocal() as session:
                user = get_primary_user(session)
                record = session.execute(
                    select(Note).where(Note.id == note_uuid, Note.user_id == user.id)
                ).scalar_one_or_none()
                if record is None:
                    raise ValueError('note not found')
                highlight = session.execute(
                    select(Highlight).where(
                        Highlight.note_id == record.id,
                        Highlight.user_id == user.id,
                    )
                ).scalar_one_or_none()
                if highlight is not None:
                    highlight.note_id = None
                session.delete(record)
                session.commit()
                return NoteDeleteResponse(id=note_id, deleted=True)
        except SQLAlchemyError:
            pass

    seed_store()
    with STORE.lock:
        for item in STORE.items.values():
            notes = list(item.get('notes', []))
            next_notes = [record for record in notes if record.get('id') != note_id]
            if len(next_notes) != len(notes):
                item['notes'] = next_notes
                for highlight in item.get('highlights', []):
                    if highlight.get('note_id') == note_id:
                        highlight['note_id'] = None
                        highlight['updated_at'] = now_utc()
                item['updated_at'] = now_utc()
                return NoteDeleteResponse(id=note_id, deleted=True)
    raise ValueError('note not found')
