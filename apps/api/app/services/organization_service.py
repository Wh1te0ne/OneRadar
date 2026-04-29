from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import Collection, CollectionItem, ContentItem, ContentItemTag, Tag
from app.db.session import SessionLocal
from app.schemas.organization import (
    CollectionCreateRequest,
    CollectionEntry,
    CollectionItemRequest,
    CollectionListResponse,
    TagEntry,
    TagListResponse,
    TagSetRequest,
)
from app.services.db_access import get_primary_user
from app.services.store import STORE, now_utc, seed_store


def normalize_label(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def normalize_key(value: str | None) -> str:
    return normalize_label(value).casefold()


def _uuid(value: str | None) -> UUID | None:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _dedupe_tag_names(names: list[str]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw_name in names:
        name = normalize_label(raw_name)
        key = normalize_key(name)
        if not name or not key or key in seen:
            continue
        seen.add(key)
        result.append((name, key))
    return result


def _tag_entry(tag: Tag) -> TagEntry:
    return TagEntry(id=tag.normalized_name, name=tag.name)


def _collection_entry(collection: Collection, item_count: int = 0) -> CollectionEntry:
    return CollectionEntry(
        id=str(collection.id),
        name=collection.name,
        description=collection.description,
        is_favorite=bool(collection.is_favorite),
        item_count=item_count,
        created_at=collection.created_at,
        updated_at=collection.updated_at,
    )


def set_item_tags(item_id: str, payload: TagSetRequest) -> TagListResponse:
    item_uuid = _uuid(item_id)
    pairs = _dedupe_tag_names(payload.tags)
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

                tags: list[Tag] = []
                for name, key in pairs:
                    tag = session.execute(
                        select(Tag).where(Tag.user_id == user.id, Tag.normalized_name == key)
                    ).scalar_one_or_none()
                    if tag is None:
                        tag = Tag(user_id=user.id, name=name, normalized_name=key)
                        session.add(tag)
                        session.flush()
                    tags.append(tag)

                session.execute(
                    delete(ContentItemTag).where(ContentItemTag.content_item_id == item.id)
                )
                for tag in tags:
                    session.add(ContentItemTag(content_item_id=item.id, tag_id=tag.id, score=None))
                raw_meta = dict(item.raw_meta or {})
                raw_meta['tags'] = [tag.name for tag in tags]
                item.raw_meta = raw_meta
                session.commit()
                return TagListResponse(items=[_tag_entry(tag) for tag in tags])
        except SQLAlchemyError:
            pass

    seed_store()
    with STORE.lock:
        item = STORE.items.get(item_id)
        if item is None:
            raise ValueError('item not found')
        item['tags'] = [name for name, _key in pairs]
        item['updated_at'] = now_utc()
        return TagListResponse(items=[TagEntry(id=key, name=name) for name, key in pairs])


def list_item_tags(item_id: str) -> TagListResponse:
    item_uuid = _uuid(item_id)
    if item_uuid is not None:
        try:
            with SessionLocal() as session:
                user = get_primary_user(session)
                rows = session.execute(
                    select(Tag)
                    .join(ContentItemTag, ContentItemTag.tag_id == Tag.id)
                    .where(ContentItemTag.content_item_id == item_uuid, Tag.user_id == user.id)
                    .order_by(Tag.name.asc())
                ).scalars()
                return TagListResponse(items=[_tag_entry(tag) for tag in rows])
        except SQLAlchemyError:
            pass

    seed_store()
    item = STORE.items.get(item_id)
    if item is None:
        raise ValueError('item not found')
    return TagListResponse(
        items=[
            TagEntry(id=key, name=name)
            for name, key in _dedupe_tag_names(list(item.get('tags', [])))
        ]
    )


def _collection_count(session, collection_id: UUID) -> int:
    return int(
        session.execute(
            select(func.count())
            .select_from(CollectionItem)
            .where(CollectionItem.collection_id == collection_id)
        ).scalar_one()
    )


def create_collection(payload: CollectionCreateRequest) -> CollectionEntry:
    name = normalize_label(payload.name)
    if not name:
        raise ValueError('collection name is required')
    try:
        with SessionLocal() as session:
            user = get_primary_user(session)
            existing = session.execute(
                select(Collection).where(Collection.user_id == user.id, Collection.name == name)
            ).scalar_one_or_none()
            if existing is not None:
                return _collection_entry(existing, _collection_count(session, existing.id))
            collection = Collection(
                user_id=user.id,
                name=name,
                description=normalize_label(payload.description) or None,
                is_favorite=False,
            )
            session.add(collection)
            session.commit()
            return _collection_entry(collection, 0)
    except SQLAlchemyError:
        seed_store()
        with STORE.lock:
            for record in STORE.collections.values():
                if normalize_key(str(record.get('name'))) == normalize_key(name):
                    return _store_collection_entry(record)
            collection_id = str(uuid4())
            record = {
                'id': collection_id,
                'name': name,
                'description': normalize_label(payload.description) or None,
                'is_favorite': False,
                'item_ids': [],
                'created_at': now_utc(),
                'updated_at': now_utc(),
            }
            STORE.collections[collection_id] = record
            return _store_collection_entry(record)


def _store_collection_entry(record: dict[str, object]) -> CollectionEntry:
    item_ids = record.get('item_ids') or []
    return CollectionEntry(
        id=str(record['id']),
        name=str(record['name']),
        description=str(record['description']) if record.get('description') else None,
        is_favorite=bool(record.get('is_favorite', False)),
        item_count=len(item_ids) if isinstance(item_ids, list) else 0,
        created_at=record.get('created_at'),
        updated_at=record.get('updated_at'),
    )


def list_collections() -> CollectionListResponse:
    try:
        with SessionLocal() as session:
            user = get_primary_user(session)
            rows = session.execute(
                select(Collection)
                .where(Collection.user_id == user.id)
                .order_by(Collection.created_at.desc())
            ).scalars()
            return CollectionListResponse(
                items=[_collection_entry(row, _collection_count(session, row.id)) for row in rows]
            )
    except SQLAlchemyError:
        seed_store()
        return CollectionListResponse(
            items=[_store_collection_entry(record) for record in STORE.collections.values()]
        )


def get_collection(collection_id: str) -> CollectionEntry:
    collection_uuid = _uuid(collection_id)
    if collection_uuid is not None:
        try:
            with SessionLocal() as session:
                user = get_primary_user(session)
                collection = session.execute(
                    select(Collection).where(
                        Collection.id == collection_uuid,
                        Collection.user_id == user.id,
                    )
                ).scalar_one_or_none()
                if collection is None:
                    raise ValueError('collection not found')
                return _collection_entry(collection, _collection_count(session, collection.id))
        except SQLAlchemyError:
            pass

    seed_store()
    record = STORE.collections.get(collection_id)
    if record is None:
        raise ValueError('collection not found')
    return _store_collection_entry(record)


def add_item_to_collection(collection_id: str, payload: CollectionItemRequest) -> CollectionEntry:
    collection_uuid = _uuid(collection_id)
    item_uuid = _uuid(payload.item_id)
    if collection_uuid is not None and item_uuid is not None:
        try:
            with SessionLocal() as session:
                user = get_primary_user(session)
                collection = session.execute(
                    select(Collection).where(
                        Collection.id == collection_uuid,
                        Collection.user_id == user.id,
                    )
                ).scalar_one_or_none()
                item = session.execute(
                    select(ContentItem).where(
                        ContentItem.id == item_uuid,
                        ContentItem.user_id == user.id,
                    )
                ).scalar_one_or_none()
                if collection is None:
                    raise ValueError('collection not found')
                if item is None:
                    raise ValueError('item not found')
                existing = session.get(CollectionItem, (collection.id, item.id))
                if existing is None:
                    session.add(
                        CollectionItem(collection_id=collection.id, content_item_id=item.id)
                    )
                session.commit()
                return _collection_entry(collection, _collection_count(session, collection.id))
        except SQLAlchemyError:
            pass

    seed_store()
    with STORE.lock:
        collection = STORE.collections.get(collection_id)
        if collection is None:
            raise ValueError('collection not found')
        if payload.item_id not in STORE.items:
            raise ValueError('item not found')
        item_ids = list(collection.get('item_ids') or [])
        if payload.item_id not in item_ids:
            item_ids.append(payload.item_id)
        collection['item_ids'] = item_ids
        collection['updated_at'] = now_utc()
        return _store_collection_entry(collection)


def remove_item_from_collection(collection_id: str, item_id: str) -> CollectionEntry:
    collection_uuid = _uuid(collection_id)
    item_uuid = _uuid(item_id)
    if collection_uuid is not None and item_uuid is not None:
        try:
            with SessionLocal() as session:
                user = get_primary_user(session)
                collection = session.execute(
                    select(Collection).where(
                        Collection.id == collection_uuid,
                        Collection.user_id == user.id,
                    )
                ).scalar_one_or_none()
                if collection is None:
                    raise ValueError('collection not found')
                membership = session.get(CollectionItem, (collection.id, item_uuid))
                if membership is not None:
                    session.delete(membership)
                session.commit()
                return _collection_entry(collection, _collection_count(session, collection.id))
        except SQLAlchemyError:
            pass

    seed_store()
    with STORE.lock:
        collection = STORE.collections.get(collection_id)
        if collection is None:
            raise ValueError('collection not found')
        item_ids = [value for value in list(collection.get('item_ids') or []) if value != item_id]
        collection['item_ids'] = item_ids
        collection['updated_at'] = now_utc()
        return _store_collection_entry(collection)
