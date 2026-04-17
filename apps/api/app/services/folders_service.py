from __future__ import annotations

from collections import defaultdict
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import ContentItem, Folder
from app.db.session import SessionLocal
from app.schemas.folders import (
    FolderCreateRequest,
    FolderDeleteResponse,
    FolderEntry,
    FolderListResponse,
    FolderUpdateRequest,
    MoveItemRequest,
    MoveItemResponse,
)
from app.services.db_access import get_primary_user
from app.services.store import STORE, now_utc, seed_store


INBOX_FOLDER_ID = "inbox"
INBOX_FOLDER_NAME = "稍后阅读"
INBOX_NORMALIZED_NAME = "inbox"


def normalize_folder_identifier(folder_id: str | None) -> str:
    value = (folder_id or "").strip()
    if not value or value.casefold() == INBOX_FOLDER_ID:
        return INBOX_FOLDER_ID
    return value


def normalize_folder_name_value(name: str | None) -> str:
    return (name or "").strip()


def normalize_folder_slug(name: str | None) -> str:
    value = normalize_folder_name_value(name)
    return value.casefold() if value else ""


def build_folder_meta(
    folder_id: str | None = None,
    folder_name: str | None = None,
    is_inbox: bool | None = None,
) -> dict[str, object]:
    normalized_id = normalize_folder_identifier(folder_id)
    normalized_name = normalize_folder_name_value(folder_name) or (
        INBOX_FOLDER_NAME if normalized_id == INBOX_FOLDER_ID else "未命名文件夹"
    )
    normalized_is_inbox = bool(is_inbox) if is_inbox is not None else normalized_id == INBOX_FOLDER_ID
    return {
        "folder_id": normalized_id,
        "folder_name": normalized_name,
        "is_inbox": normalized_is_inbox,
    }


def extract_folder_meta(raw_meta: dict[str, object] | None) -> tuple[str, str, bool]:
    payload = raw_meta or {}
    folder_id = normalize_folder_identifier(str(payload.get("folder_id")) if payload.get("folder_id") else None)
    folder_name = normalize_folder_name_value(
        str(payload.get("folder_name")) if payload.get("folder_name") else None
    ) or (INBOX_FOLDER_NAME if folder_id == INBOX_FOLDER_ID else "未命名文件夹")
    is_inbox = bool(payload.get("is_inbox")) or folder_id == INBOX_FOLDER_ID
    return folder_id, folder_name, is_inbox


def _folder_entry_from_db(folder: Folder, item_count: int = 0) -> FolderEntry:
    return FolderEntry(
        id=str(folder.id),
        name=folder.name,
        is_builtin=bool(folder.is_inbox),
        item_count=item_count,
        created_at=folder.created_at,
        updated_at=folder.updated_at,
    )


def _folder_entry_from_store(record: dict[str, object], item_count: int = 0) -> FolderEntry:
    return FolderEntry(
        id=str(record["id"]),
        name=str(record["name"]),
        is_builtin=bool(record.get("is_builtin", False)),
        item_count=item_count,
        created_at=record.get("created_at"),
        updated_at=record.get("updated_at"),
    )


def _ensure_inbox_folder(session) -> Folder:
    user = get_primary_user(session)
    folder = session.execute(
        select(Folder).where(Folder.user_id == user.id, Folder.is_inbox.is_(True))
    ).scalar_one_or_none()
    if folder is not None:
        folder.name = INBOX_FOLDER_NAME
        folder.normalized_name = INBOX_NORMALIZED_NAME
        folder.is_inbox = True
        return folder

    folder = session.execute(
        select(Folder).where(Folder.user_id == user.id, Folder.normalized_name == INBOX_NORMALIZED_NAME)
    ).scalar_one_or_none()
    if folder is not None:
        folder.name = INBOX_FOLDER_NAME
        folder.normalized_name = INBOX_NORMALIZED_NAME
        folder.is_inbox = True
        return folder

    folder = Folder(
        user_id=user.id,
        name=INBOX_FOLDER_NAME,
        normalized_name=INBOX_NORMALIZED_NAME,
        is_inbox=True,
        sort_order=0,
        color=None,
    )
    session.add(folder)
    session.flush()
    return folder


def resolve_folder(session, folder_id: str | None) -> Folder | None:
    identifier = normalize_folder_identifier(folder_id)
    if identifier == INBOX_FOLDER_ID:
        return _ensure_inbox_folder(session)

    try:
        folder_uuid = UUID(identifier)
    except ValueError:
        folder_uuid = None

    if folder_uuid is not None:
        folder = session.get(Folder, folder_uuid)
        if folder is not None:
            return folder

    user = get_primary_user(session)
    normalized_name = normalize_folder_slug(identifier)
    if not normalized_name:
        return None
    return session.execute(
        select(Folder).where(Folder.user_id == user.id, Folder.normalized_name == normalized_name)
    ).scalar_one_or_none()


def _folder_count(session, folder: Folder) -> int:
    criterion = or_(ContentItem.folder_id == folder.id, ContentItem.folder_id.is_(None)) if folder.is_inbox else ContentItem.folder_id == folder.id
    return int(
        session.execute(
            select(func.count()).select_from(ContentItem).where(ContentItem.user_id == folder.user_id, criterion)
        ).scalar_one()
    )


def get_folder_item_count(session, folder: Folder) -> int:
    return _folder_count(session, folder)


def get_or_create_inbox_folder(session) -> Folder:
    return _ensure_inbox_folder(session)


def _folder_entries_from_session(session) -> list[FolderEntry]:
    user = get_primary_user(session)
    inbox = _ensure_inbox_folder(session)
    folders = session.execute(
        select(Folder).where(Folder.user_id == user.id).order_by(Folder.is_inbox.desc(), Folder.sort_order.asc(), Folder.created_at.asc())
    ).scalars().all()

    seen_ids: set[str] = set()
    entries: list[FolderEntry] = []
    for folder in folders:
        seen_ids.add(str(folder.id))
        entries.append(_folder_entry_from_db(folder, _folder_count(session, folder)))

    if str(inbox.id) not in seen_ids:
        entries.insert(0, _folder_entry_from_db(inbox, _folder_count(session, inbox)))

    return sorted(entries, key=lambda entry: (entry.id != str(inbox.id), entry.name))


def list_folders() -> FolderListResponse:
    try:
        with SessionLocal() as session:
            return FolderListResponse(items=_folder_entries_from_session(session))
    except SQLAlchemyError:
        seed_store()
        with STORE.lock:
            counts: dict[str, int] = defaultdict(int)
            for record in STORE.items.values():
                folder_id = str(record.get("folder_id", INBOX_FOLDER_ID) or INBOX_FOLDER_ID)
                counts[folder_id] += 1
            entries = [
                _folder_entry_from_store(record, counts.get(folder_id, 0))
                for folder_id, record in STORE.folders.items()
            ]
            if all(entry.id != INBOX_FOLDER_ID for entry in entries):
                entries.insert(
                    0,
                    FolderEntry(
                        id=INBOX_FOLDER_ID,
                        name=INBOX_FOLDER_NAME,
                        is_builtin=True,
                        item_count=counts.get(INBOX_FOLDER_ID, 0),
                        created_at=now_utc(),
                        updated_at=now_utc(),
                    ),
                )
            return FolderListResponse(items=sorted(entries, key=lambda entry: (entry.id != INBOX_FOLDER_ID, entry.name)))


def create_folder(payload: FolderCreateRequest) -> FolderEntry:
    name = normalize_folder_name_value(payload.name)
    if not name:
        raise ValueError("folder name is required")

    try:
        with SessionLocal() as session:
            user = get_primary_user(session)
            _ensure_inbox_folder(session)
            normalized_name = normalize_folder_slug(name)
            existing = session.execute(
                select(Folder).where(Folder.user_id == user.id, Folder.normalized_name == normalized_name)
            ).scalar_one_or_none()
            if existing is not None:
                return _folder_entry_from_db(existing, _folder_count(session, existing))

            next_sort_order = int(
                session.execute(
                    select(func.coalesce(func.max(Folder.sort_order), 0)).where(Folder.user_id == user.id)
                ).scalar_one()
            )
            folder = Folder(
                user_id=user.id,
                name=name,
                normalized_name=normalized_name,
                is_inbox=False,
                sort_order=next_sort_order + 1,
                color=None,
            )
            session.add(folder)
            session.commit()
            return _folder_entry_from_db(folder, 0)
    except SQLAlchemyError:
        seed_store()
        with STORE.lock:
            for record in STORE.folders.values():
                if str(record.get("name", "")).strip().casefold() == name.casefold():
                    return _folder_entry_from_store(record)
            folder_id = str(uuid4())
            record = {
                "id": folder_id,
                "name": name,
                "is_builtin": False,
                "created_at": now_utc(),
                "updated_at": now_utc(),
            }
            STORE.folders[folder_id] = record
            return _folder_entry_from_store(record)


def update_folder(folder_id: str, payload: FolderUpdateRequest) -> FolderEntry:
    name = normalize_folder_name_value(payload.name)
    if not name:
        raise ValueError("folder name is required")

    try:
        with SessionLocal() as session:
            user = get_primary_user(session)
            folder = resolve_folder(session, folder_id)
            if folder is None:
                raise ValueError("folder not found")
            if folder.is_inbox:
                return _folder_entry_from_db(folder, _folder_count(session, folder))

            normalized_name = normalize_folder_slug(name)
            conflict = session.execute(
                select(Folder).where(
                    Folder.user_id == user.id,
                    Folder.normalized_name == normalized_name,
                    Folder.id != folder.id,
                )
            ).scalar_one_or_none()
            if conflict is not None:
                return _folder_entry_from_db(conflict, _folder_count(session, conflict))

            folder.name = name
            folder.normalized_name = normalized_name
            session.commit()
            return _folder_entry_from_db(folder, _folder_count(session, folder))
    except SQLAlchemyError:
        seed_store()
        with STORE.lock:
            record = STORE.folders.get(normalize_folder_identifier(folder_id))
            if record is None:
                for candidate in STORE.folders.values():
                    if str(candidate.get("name", "")).strip().casefold() == normalize_folder_slug(folder_id):
                        record = candidate
                        break
            if record is None:
                raise ValueError("folder not found")
            if bool(record.get("is_builtin", False)):
                return _folder_entry_from_store(record)
            record["name"] = name
            record["updated_at"] = now_utc()
            return _folder_entry_from_store(record)


def delete_folder(folder_id: str) -> FolderDeleteResponse:
    try:
        with SessionLocal() as session:
            folder = resolve_folder(session, folder_id)
            if folder is None or folder.is_inbox:
                return FolderDeleteResponse(id=str(normalize_folder_identifier(folder_id)), deleted=False, moved_item_count=0)

            inbox = _ensure_inbox_folder(session)
            items = session.execute(
                select(ContentItem).where(ContentItem.user_id == folder.user_id, ContentItem.folder_id == folder.id)
            ).scalars().all()
            for item in items:
                item.folder_id = inbox.id
                item.raw_meta = {
                    **(item.raw_meta or {}),
                    **build_folder_meta(str(inbox.id), inbox.name, True),
                }
            moved = len(items)
            session.delete(folder)
            session.commit()
            return FolderDeleteResponse(id=str(folder.id), deleted=True, moved_item_count=moved)
    except SQLAlchemyError:
        seed_store()
        moved = 0
        with STORE.lock:
            target_id = normalize_folder_identifier(folder_id)
            if target_id == INBOX_FOLDER_ID:
                return FolderDeleteResponse(id=INBOX_FOLDER_ID, deleted=False, moved_item_count=0)
            for record in STORE.items.values():
                if str(record.get("folder_id", INBOX_FOLDER_ID)) != target_id:
                    continue
                record["folder_id"] = INBOX_FOLDER_ID
                record["folder_name"] = INBOX_FOLDER_NAME
                record["is_inbox"] = True
                record["updated_at"] = now_utc()
                moved += 1
            record = STORE.folders.pop(target_id, None)
        return FolderDeleteResponse(id=str(record["id"] if record else target_id), deleted=bool(record), moved_item_count=moved)


def move_item_to_folder(item_id: str, payload: MoveItemRequest) -> MoveItemResponse:
    target_identifier = normalize_folder_identifier(payload.folder_id)
    try:
        with SessionLocal() as session:
            item = session.get(ContentItem, UUID(item_id))
            if item is None:
                raise ValueError("item not found")

            target_folder = resolve_folder(session, target_identifier)
            if target_folder is None:
                raise ValueError("folder not found")

            item.folder_id = target_folder.id
            item.raw_meta = {
                **(item.raw_meta or {}),
                **build_folder_meta(str(target_folder.id), target_folder.name, bool(target_folder.is_inbox)),
            }
            session.commit()
            return MoveItemResponse(
                uid=str(item.id),
                folder_id=str(target_folder.id),
                folder_name=target_folder.name,
                is_inbox=bool(target_folder.is_inbox),
            )
    except (SQLAlchemyError, ValueError):
        seed_store()
        with STORE.lock:
            record = STORE.items.get(item_id)
            if record is None:
                raise ValueError("item not found")
            if target_identifier == INBOX_FOLDER_ID:
                folder_record = STORE.folders.get(INBOX_FOLDER_ID)
                if folder_record is None:
                    folder_record = {
                        "id": INBOX_FOLDER_ID,
                        "name": INBOX_FOLDER_NAME,
                        "is_builtin": True,
                        "created_at": now_utc(),
                        "updated_at": now_utc(),
                    }
                    STORE.folders[INBOX_FOLDER_ID] = folder_record
                record["folder_id"] = INBOX_FOLDER_ID
                record["folder_name"] = INBOX_FOLDER_NAME
                record["is_inbox"] = True
                record["updated_at"] = now_utc()
                return MoveItemResponse(uid=item_id, folder_id=INBOX_FOLDER_ID, folder_name=INBOX_FOLDER_NAME, is_inbox=True)

            folder_record = STORE.folders.get(target_identifier)
            if folder_record is None:
                for candidate in STORE.folders.values():
                    if str(candidate.get("name", "")).strip().casefold() == normalize_folder_slug(target_identifier):
                        folder_record = candidate
                        break
            if folder_record is None:
                raise ValueError("folder not found")
            record["folder_id"] = str(folder_record["id"])
            record["folder_name"] = str(folder_record["name"])
            record["is_inbox"] = bool(folder_record.get("is_builtin", False))
            record["updated_at"] = now_utc()
            return MoveItemResponse(
                uid=item_id,
                folder_id=str(folder_record["id"]),
                folder_name=str(folder_record["name"]),
                is_inbox=bool(folder_record.get("is_builtin", False)),
            )

