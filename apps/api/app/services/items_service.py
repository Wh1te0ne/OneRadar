from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from app.db.models import ContentItem, ContentParsedDocument, ProcessingTask, Summary, Transcript as TranscriptModel
from app.db.session import SessionLocal
from app.schemas.common import ContentType, ItemStatus, ReadingState, TaskStatus
from app.schemas.items import (
    ImportItemResponse,
    ItemDeleteResponse,
    ItemDetailResponse,
    ItemListEntry,
    ItemListResponse,
    ItemReprocessResponse,
    ParsedDocument,
    SummaryEntry,
    TagEntry,
    Transcript,
)
from app.services.db_access import get_primary_user
from app.services.folders_service import (
    INBOX_FOLDER_ID,
    INBOX_FOLDER_NAME,
    build_folder_meta,
    extract_folder_meta,
    normalize_folder_identifier,
    resolve_folder,
)
from app.services.store import STORE, now_utc, seed_store
from app.services.url_safety import validate_public_http_url


DEFAULT_PARSED_DOCUMENT = {
    "plain_text": "",
    "structured_blocks": [],
    "parser_name": None,
    "parser_version": None,
}

DEFAULT_READING_STATE = {
    "progress_percent": 0,
    "last_read_at": None,
    "is_archived": False,
    "is_favorited": False,
}

TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "spm",
    "spm_id_from",
    "utm_campaign",
    "utm_content",
    "utm_id",
    "utm_medium",
    "utm_name",
    "utm_source",
    "utm_term",
    "vd_source",
}


def normalize_source_url(url: str) -> str:
    candidate = url.strip()
    if not candidate:
        return ""

    parsed = urlsplit(candidate)
    if not parsed.scheme or not parsed.netloc:
        return candidate

    hostname = (parsed.hostname or "").casefold()
    if hostname == "m.bilibili.com":
        hostname = "www.bilibili.com"
    port = parsed.port
    if parsed.scheme.casefold() == "http" and port == 80:
        port = None
    elif parsed.scheme.casefold() == "https" and port == 443:
        port = None
    if parsed.username:
        auth = parsed.username
        if parsed.password:
            auth = f"{auth}:{parsed.password}"
        netloc = f"{auth}@{hostname}"
    else:
        netloc = hostname
    if port is not None:
        netloc = f"{netloc}:{port}"

    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=False)
        if key.casefold() not in TRACKING_QUERY_KEYS
    ]
    normalized_query = urlencode(sorted(query_items), doseq=True)
    normalized_path = parsed.path.rstrip("/") or "/"

    return urlunsplit(
        (
            parsed.scheme.casefold(),
            netloc,
            normalized_path,
            normalized_query,
            "",
        )
    )


def _normalize_content_type(source_hint: str | None, url: str) -> ContentType:
    normalized_hint = (source_hint or "").strip().casefold()
    normalized_url = url.casefold()
    if normalized_hint in {"bilibili", "bilibili_video"} or any(
        host in normalized_url for host in ("bilibili.com", "b23.tv", "bili22.cn", "bili23.cn", "bili2233.cn")
    ):
        return ContentType.bilibili_video
    return ContentType.article


def _source_platform(content_type: ContentType) -> str:
    return "bilibili" if content_type == ContentType.bilibili_video else "web"


def _default_folder_meta(folder_id: str, folder_name: str, is_inbox: bool) -> dict[str, object]:
    return build_folder_meta(folder_id, folder_name, is_inbox)


def _item_folder_info(item: ContentItem) -> tuple[str, str, bool]:
    folder = getattr(item, "folder", None)
    if folder is not None:
        return str(folder.id), folder.name, bool(folder.is_inbox)
    return extract_folder_meta(item.raw_meta)


def _item_meta(item: ContentItem) -> dict[str, object]:
    raw_meta = item.raw_meta or {}
    metadata = raw_meta.get("metadata") or {}
    return {
        "author_name": item.author_name or raw_meta.get("author_name"),
        "published_at": item.published_at or raw_meta.get("published_at"),
        "site_name": raw_meta.get("site_name") or metadata.get("site_name"),
    }


def _item_uid(item: ContentItem) -> str:
    return str(item.id)


def _latest_parsed_document_record(item: ContentItem) -> ContentParsedDocument | None:
    documents = list(item.content_parsed_documents or [])
    if not documents:
        return None
    return max(documents, key=lambda record: (record.created_at, record.updated_at, str(record.id)))


def _item_document(item: ContentItem) -> ParsedDocument:
    parsed_document_record = _latest_parsed_document_record(item)
    if parsed_document_record is not None:
        return ParsedDocument(
            plain_text=parsed_document_record.plain_text,
            structured_blocks=list(parsed_document_record.structured_blocks or []),
            parser_name=parsed_document_record.parser_name,
            parser_version=parsed_document_record.parser_version,
        )

    raw_meta = item.raw_meta or {}
    parsed_document = raw_meta.get("parsed_document") or DEFAULT_PARSED_DOCUMENT
    return ParsedDocument(
        plain_text=str(parsed_document.get("plain_text", "")),
        structured_blocks=list(parsed_document.get("structured_blocks", [])),
        parser_name=parsed_document.get("parser_name"),
        parser_version=parsed_document.get("parser_version"),
    )


def _latest_transcript_record(item: ContentItem) -> TranscriptModel | None:
    transcripts = list(item.transcripts or [])
    if not transcripts:
        return None
    return max(transcripts, key=lambda record: (record.created_at, record.updated_at, str(record.id)))


def _item_transcript(item: ContentItem) -> Transcript | None:
    transcript_record = _latest_transcript_record(item)
    if transcript_record is not None:
        return Transcript(
            transcript_type=transcript_record.transcript_type,
            language=transcript_record.language,
            full_text=transcript_record.full_text,
            segments=list(transcript_record.segments or []),
            provider_name=transcript_record.provider_name,
            model_name=transcript_record.model_name,
        )

    raw_meta = item.raw_meta or {}
    transcript = raw_meta.get("transcript")
    if not transcript:
        return None
    return Transcript(**transcript)


def _sorted_summary_records(item: ContentItem) -> list[Summary]:
    records = list(item.summaries or [])
    return sorted(records, key=lambda record: (record.summary_type, record.version, record.created_at, str(record.id)))


def _item_summaries(item: ContentItem) -> list[SummaryEntry]:
    summary_records = _sorted_summary_records(item)
    if summary_records:
        return [
            SummaryEntry(
                summary_type=record.summary_type,
                content=record.content,
                model_name=record.model_name,
                version=record.version,
            )
            for record in summary_records
        ]

    raw_meta = item.raw_meta or {}
    summaries = raw_meta.get("summaries") or []
    return [SummaryEntry(**summary) for summary in summaries]


def _item_highlights(item: ContentItem) -> list[dict[str, object]]:
    raw_meta = item.raw_meta or {}
    return list(raw_meta.get("highlights") or [])


def _item_notes(item: ContentItem) -> list[dict[str, object]]:
    raw_meta = item.raw_meta or {}
    return list(raw_meta.get("notes") or [])


def _item_tags(item: ContentItem) -> list[TagEntry]:
    raw_meta = item.raw_meta or {}
    tags = raw_meta.get("tags") or []
    return [TagEntry(name=str(tag)) for tag in tags]


def _item_collections(item: ContentItem) -> list[dict[str, object]]:
    raw_meta = item.raw_meta or {}
    return list(raw_meta.get("collections") or [])


def _item_reading_state(item: ContentItem) -> ReadingState:
    raw_meta = item.raw_meta or {}
    fallback_state = raw_meta.get("reading_state") or DEFAULT_READING_STATE
    reading_state_record = item.reading_state
    if reading_state_record is not None:
        return ReadingState(
            progress_percent=reading_state_record.progress_percent,
            last_read_at=reading_state_record.last_read_at,
            is_archived=reading_state_record.is_archived,
            is_favorited=bool(fallback_state.get("is_favorited", False)),
        )
    return ReadingState.model_validate(fallback_state)


def _meta_list_values(raw_meta: dict[str, object] | None, key: str) -> list[str]:
    values = (raw_meta or {}).get(key)
    if not isinstance(values, Iterable) or isinstance(values, (str, bytes, dict)):
        return []
    normalized: list[str] = []
    for value in values:
        if isinstance(value, dict):
            name = value.get("name")
            if isinstance(name, str) and name.strip():
                normalized.append(name.strip())
        elif isinstance(value, str) and value.strip():
            normalized.append(value.strip())
    return normalized


def _item_search_text(item: ContentItem) -> str:
    raw_meta = item.raw_meta or {}
    parsed_document = _item_document(item)
    transcript = _item_transcript(item)
    summaries = _item_summaries(item)
    tags = _meta_list_values(raw_meta, "tags")
    collections = _meta_list_values(raw_meta, "collections")
    summary_text = " ".join(summary.content.strip() for summary in summaries if summary.content.strip())
    return " ".join(
        filter(
            None,
            [
                item.title,
                item.source_url,
                str(item.author_name or raw_meta.get("author_name", "")).strip(),
                str(raw_meta.get("site_name", "")).strip(),
                parsed_document.plain_text.strip(),
                (transcript.full_text if transcript else "").strip(),
                summary_text,
                " ".join(tags),
                " ".join(collections),
            ],
        )
    ).casefold()


def _preferred_summary_text(item: ContentItem) -> str | None:
    summaries = _item_summaries(item)
    preferred_order = {"one_line": 0, "short": 1, "key_points": 2, "outline": 3}
    if summaries:
        chosen = min(
            summaries,
            key=lambda entry: (preferred_order.get(entry.summary_type.value, 99), entry.version),
        )
        content = chosen.content.strip()
        if content:
            return content

    parsed_document_record = _latest_parsed_document_record(item)
    if parsed_document_record is not None and parsed_document_record.excerpt:
        excerpt = parsed_document_record.excerpt.strip()
        if excerpt:
            return excerpt

    transcript_record = _latest_transcript_record(item)
    if transcript_record is not None:
        transcript_preview = transcript_record.full_text.strip()
        if transcript_preview:
            return transcript_preview[:180]

    document = _item_document(item)
    if document.plain_text.strip():
        return document.plain_text.strip()[:180]
    return None


def _item_tags_for_list(item: ContentItem) -> list[str]:
    raw_meta = item.raw_meta or {}
    return _meta_list_values(raw_meta, "tags")


def _item_list_entry(item: ContentItem) -> ItemListEntry:
    reading_state = _item_reading_state(item)
    folder_id, folder_name, is_inbox = _item_folder_info(item)
    return ItemListEntry(
        uid=_item_uid(item),
        id=str(item.id),
        title=item.title,
        content_type=ContentType(item.content_type),
        source_url=item.source_url,
        status=ItemStatus(item.status),
        folder_id=folder_id,
        folder_name=folder_name,
        is_inbox=is_inbox,
        is_read=bool(reading_state.progress_percent >= 100),
        is_favorited=reading_state.is_favorited,
        created_at=item.created_at,
        updated_at=item.updated_at,
        summary=_preferred_summary_text(item),
        tags=_item_tags_for_list(item),
    )


def _item_detail_response(item: ContentItem) -> ItemDetailResponse:
    folder_id, folder_name, is_inbox = _item_folder_info(item)
    return ItemDetailResponse(
        uid=_item_uid(item),
        id=str(item.id),
        title=item.title,
        content_type=ContentType(item.content_type),
        source_url=item.source_url,
        status=ItemStatus(item.status),
        folder_id=folder_id,
        folder_name=folder_name,
        is_inbox=is_inbox,
        metadata=_item_meta(item),
        parsed_document=_item_document(item),
        transcript=_item_transcript(item),
        summaries=_item_summaries(item),
        highlights=_item_highlights(item),
        notes=_item_notes(item),
        tags=_item_tags(item),
        collections=_item_collections(item),
        reading_state=_item_reading_state(item),
    )


def _fallback_import(url: str, source_hint: str | None) -> ImportItemResponse:
    seed_store()
    normalized_url = normalize_source_url(url)
    if not normalized_url:
        raise ValueError("url is required")
    validate_public_http_url(normalized_url)
    content_type = _normalize_content_type(source_hint, normalized_url)

    with STORE.lock:
        existing = next((item for item in STORE.items.values() if item["source_url"] == normalized_url), None)
        if existing is not None:
            folder_id = str(existing.get("folder_id", INBOX_FOLDER_ID))
            folder_name = str(existing.get("folder_name", INBOX_FOLDER_NAME))
            return ImportItemResponse(
                uid=str(existing["id"]),
                item_id=str(existing["id"]),
                existing_uid=str(existing["id"]),
                task_id=None,
                status="already_exists",
                content_type=existing["content_type"],
                folder_id=folder_id,
                folder_name=folder_name,
                is_duplicate=True,
            )

        item_id = str(uuid4())
        task_id = str(uuid4())
        item_record = {
            "id": item_id,
            "uid": item_id,
            "title": "新导入内容",
            "content_type": content_type,
            "source_url": normalized_url,
            "folder_id": INBOX_FOLDER_ID,
            "folder_name": INBOX_FOLDER_NAME,
            "is_inbox": True,
            "status": ItemStatus.pending.value,
            "parsed_document": {
                "plain_text": "",
                "structured_blocks": [],
                "parser_name": None,
                "parser_version": None,
                "excerpt": None,
            },
            "transcript": None,
            "summaries": [],
            "highlights": [],
            "notes": [],
            "tags": [],
            "collections": [],
            "reading_state": DEFAULT_READING_STATE.copy(),
            "created_at": now_utc(),
            "updated_at": now_utc(),
        }
        STORE.items[item_id] = item_record
        STORE.tasks[task_id] = {
            "id": task_id,
            "item_id": item_id,
            "task_type": "fetch_meta",
            "status": "pending",
            "attempt_count": 0,
            "error_message": None,
            "created_at": now_utc(),
        }

    return ImportItemResponse(
        uid=item_id,
        item_id=item_id,
        task_id=task_id,
        status="pending",
        content_type=content_type,
        folder_id=INBOX_FOLDER_ID,
        folder_name=INBOX_FOLDER_NAME,
        is_duplicate=False,
    )


def import_item(url: str, source_hint: str | None) -> ImportItemResponse:
    try:
        with SessionLocal() as session:
            user = get_primary_user(session)
            inbox = resolve_folder(session, INBOX_FOLDER_ID)
            if inbox is None:
                raise ValueError("inbox folder not found")
            normalized_url = normalize_source_url(url)
            if not normalized_url:
                raise ValueError("url is required")
            validate_public_http_url(normalized_url)
            content_type = _normalize_content_type(source_hint, normalized_url)

            existing = session.execute(
                select(ContentItem).where(
                    ContentItem.user_id == user.id,
                    ContentItem.normalized_url == normalized_url,
                )
            ).scalar_one_or_none()
            if existing is not None:
                folder_id, folder_name, _ = _item_folder_info(existing)
                return ImportItemResponse(
                    uid=str(existing.id),
                    item_id=str(existing.id),
                    existing_uid=str(existing.id),
                    task_id=None,
                    status="already_exists",
                    content_type=ContentType(existing.content_type),
                    folder_id=folder_id,
                    folder_name=folder_name,
                    is_duplicate=True,
                )

            item = ContentItem(
                user_id=user.id,
                folder_id=inbox.id,
                content_type=content_type.value,
                source_platform=_source_platform(content_type),
                source_url=normalized_url,
                normalized_url=normalized_url,
                external_id=None,
                title="新导入内容",
                subtitle=None,
                author_name=None,
                author_id=None,
                cover_url=None,
                duration_seconds=None,
                language=None,
                status=ItemStatus.pending.value,
                visibility="private",
                raw_meta={
                    "metadata": {},
                    "parsed_document": DEFAULT_PARSED_DOCUMENT,
                    "transcript": None,
                    "summaries": [],
                    "highlights": [],
                    "notes": [],
                    "tags": [],
                    "collections": [],
                    "reading_state": DEFAULT_READING_STATE,
                    **_default_folder_meta(str(inbox.id), inbox.name, bool(inbox.is_inbox)),
                },
                fetch_hash=None,
            )
            session.add(item)
            session.flush()

            task = ProcessingTask(
                content_item_id=item.id,
                user_id=user.id,
                task_type="fetch_meta",
                status=TaskStatus.pending.value,
                priority=0,
                attempt_count=0,
                max_attempts=3,
                locked_by=None,
                payload={"source_hint": source_hint, "url": normalized_url},
                result={},
                error_message=None,
                started_at=None,
                finished_at=None,
                next_retry_at=None,
            )
            session.add(task)
            session.commit()
            folder_id, folder_name, _ = _item_folder_info(item)
            return ImportItemResponse(
                uid=str(item.id),
                item_id=str(item.id),
                task_id=str(task.id),
                status="pending",
                content_type=content_type,
                folder_id=folder_id,
                folder_name=folder_name,
                is_duplicate=False,
            )
    except SQLAlchemyError:
        return _fallback_import(url, source_hint)


def _filtered_items(records: list[ContentItem], folder_id: str | None, inbox_only: bool) -> list[ContentItem]:
    if folder_id is not None:
        target = normalize_folder_identifier(folder_id)
        if target == INBOX_FOLDER_ID:
            return [
                item
                for item in records
                if _item_folder_info(item)[2] or item.folder_id is None or _item_folder_info(item)[0] == INBOX_FOLDER_ID
            ]
        return [item for item in records if _item_folder_info(item)[0] == target]
    if inbox_only:
        return [item for item in records if _item_folder_info(item)[2] or item.folder_id is None]
    return records


def list_items(
    page: int,
    page_size: int,
    *,
    keyword: str | None = None,
    source_type: str | None = None,
    status: str | None = None,
    tag: str | None = None,
    folder_id: str | None = None,
    inbox_only: bool = False,
) -> ItemListResponse:
    try:
        with SessionLocal() as session:
            user = get_primary_user(session)
            items = list(
                session.execute(
                    select(ContentItem)
                    .options(
                        selectinload(ContentItem.folder),
                        selectinload(ContentItem.content_parsed_documents),
                        selectinload(ContentItem.transcripts),
                        selectinload(ContentItem.summaries),
                        selectinload(ContentItem.reading_state),
                    )
                    .where(ContentItem.user_id == user.id)
                    .order_by(ContentItem.created_at.desc())
                ).scalars()
            )
            items = _filtered_items(items, folder_id, inbox_only)
            items = [
                item
                for item in items
                if _matches_item_filters(
                    item,
                    keyword=keyword,
                    source_type=source_type,
                    status=status,
                    tag=tag,
                )
            ]
            start = (page - 1) * page_size
            end = start + page_size
            return ItemListResponse(
                items=[_item_list_entry(record) for record in items[start:end]],
                page=page,
                page_size=page_size,
                total=len(items),
            )
    except SQLAlchemyError:
        seed_store()
        items = sorted(STORE.items.values(), key=lambda record: record["created_at"], reverse=True)
        if folder_id is not None:
            target = normalize_folder_identifier(folder_id)
            if target == INBOX_FOLDER_ID:
                items = [
                    record
                    for record in items
                    if bool(record.get("is_inbox", False)) or str(record.get("folder_id", INBOX_FOLDER_ID)) == INBOX_FOLDER_ID
                ]
            else:
                items = [record for record in items if str(record.get("folder_id", INBOX_FOLDER_ID)) == target]
        elif inbox_only:
            items = [record for record in items if bool(record.get("is_inbox", False)) or record.get("folder_id") is None]

        normalized_keyword = (keyword or "").strip().casefold()
        normalized_source_type = (source_type or "").strip().casefold()
        normalized_status = (status or "").strip().casefold()
        normalized_tag = (tag or "").strip().casefold()

        if normalized_keyword:
            items = [
                record
                for record in items
                if normalized_keyword
                in " ".join(
                    [
                        str(record.get("title", "")),
                        str(record.get("source_url", "")),
                        str(record.get("metadata", {}).get("author_name", "")),
                        str(record.get("metadata", {}).get("site_name", "")),
                        str(record.get("parsed_document", {}).get("plain_text", "")),
                        str((record.get("transcript") or {}).get("full_text", "")),
                        " ".join(str(tag_value) for tag_value in record.get("tags", [])),
                    ]
                ).casefold()
            ]
        if normalized_source_type:
            items = [
                record
                for record in items
                if normalized_source_type
                in {
                    str(getattr(record.get("content_type", ""), "value", record.get("content_type", ""))).casefold(),
                    ("bilibili" if record.get("content_type") == ContentType.bilibili_video else "web"),
                }
            ]
        if normalized_status:
            items = [record for record in items if str(getattr(record.get("status", ""), "value", record.get("status", ""))).casefold() == normalized_status]
        if normalized_tag:
            items = [
                record
                for record in items
                if normalized_tag in {str(tag_value).casefold() for tag_value in record.get("tags", [])}
            ]

        start = (page - 1) * page_size
        end = start + page_size
        return ItemListResponse(
            items=[
                ItemListEntry(
                    uid=str(record["id"]),
                    id=str(record["id"]),
                    title=str(record["title"]),
                    content_type=record["content_type"],
                    source_url=str(record["source_url"]),
                    status=record["status"],
                    folder_id=str(record.get("folder_id", INBOX_FOLDER_ID)),
                    folder_name=str(record.get("folder_name", INBOX_FOLDER_NAME)),
                    is_inbox=bool(record.get("is_inbox", True)),
                    is_read=bool(record["reading_state"]["progress_percent"] >= 100),
                    is_favorited=bool(record["reading_state"]["is_favorited"]),
                    created_at=record["created_at"],
                    updated_at=record["updated_at"],
                    summary=(str(record.get("parsed_document", {}).get("excerpt", "")).strip() or None),
                    tags=[str(tag_value) for tag_value in record.get("tags", []) if str(tag_value).strip()],
                )
                for record in items[start:end]
            ],
            page=page,
            page_size=page_size,
            total=len(items),
        )


def get_item(item_id: str) -> ItemDetailResponse:
    try:
        with SessionLocal() as session:
            item = session.execute(
                select(ContentItem)
                .options(
                    selectinload(ContentItem.folder),
                    selectinload(ContentItem.content_parsed_documents),
                    selectinload(ContentItem.transcripts),
                    selectinload(ContentItem.summaries),
                    selectinload(ContentItem.reading_state),
                )
                .where(ContentItem.id == UUID(item_id))
            ).scalar_one_or_none()
            if item is not None:
                return _item_detail_response(item)
    except (SQLAlchemyError, ValueError):
        pass

    seed_store()
    record = STORE.items.get(item_id)
    if record is None:
        raise ValueError("item not found")
    folder_id = str(record.get("folder_id", INBOX_FOLDER_ID))
    folder_name = str(record.get("folder_name", INBOX_FOLDER_NAME))
    is_inbox = bool(record.get("is_inbox", folder_id == INBOX_FOLDER_ID))
    return ItemDetailResponse(
        uid=str(record["id"]),
        id=str(record["id"]),
        title=str(record["title"]),
        content_type=record["content_type"],
        source_url=str(record["source_url"]),
        status=record["status"],
        folder_id=folder_id,
        folder_name=folder_name,
        is_inbox=is_inbox,
        metadata=record["metadata"],
        parsed_document=ParsedDocument(**record["parsed_document"]),
        transcript=Transcript(**record["transcript"]) if record.get("transcript") else None,
        summaries=[SummaryEntry(**summary) for summary in record["summaries"]],
        highlights=record["highlights"],
        notes=record["notes"],
        tags=[TagEntry(name=str(tag)) for tag in record["tags"]],
        collections=record["collections"],
        reading_state=ReadingState.model_validate(record["reading_state"]),
    )


def delete_item(item_id: str) -> ItemDeleteResponse:
    try:
        with SessionLocal() as session:
            item = session.get(ContentItem, UUID(item_id))
            if item is None:
                raise ValueError("item not found")
            session.delete(item)
            session.commit()
            return ItemDeleteResponse(uid=str(item.id), deleted=True)
    except (SQLAlchemyError, ValueError):
        seed_store()
        with STORE.lock:
            record = STORE.items.pop(item_id, None)
        if record is None:
            raise ValueError("item not found")
        return ItemDeleteResponse(uid=item_id, deleted=True)


def reprocess_item(item_id: str) -> ItemReprocessResponse:
    try:
        with SessionLocal() as session:
            user = get_primary_user(session)
            item = session.get(ContentItem, UUID(item_id))
            if item is None:
                raise ValueError("item not found")
            task = ProcessingTask(
                content_item_id=item.id,
                user_id=user.id,
                task_type="reprocess_item",
                status=TaskStatus.retrying.value,
                priority=0,
                attempt_count=1,
                max_attempts=3,
                locked_by=None,
                payload={"steps": ["extract", "transcribe", "summarize", "index"]},
                result={},
                error_message=None,
                started_at=now_utc(),
                finished_at=None,
                next_retry_at=None,
            )
            session.add(task)
            session.commit()
            return ItemReprocessResponse(item_id=item_id, task_id=str(task.id), status="queued")
    except (SQLAlchemyError, ValueError):
        seed_store()
        task_id = str(uuid4())
        with STORE.lock:
            STORE.tasks[task_id] = {
                "id": task_id,
                "item_id": item_id,
                "task_type": "reprocess_item",
                "status": "retrying",
                "attempt_count": 1,
                "error_message": None,
                "created_at": now_utc(),
            }
        return ItemReprocessResponse(item_id=item_id, task_id=task_id, status="queued")


def _matches_item_filters(
    item: ContentItem,
    *,
    keyword: str | None,
    source_type: str | None,
    status: str | None,
    tag: str | None,
) -> bool:
    normalized_keyword = (keyword or "").strip().casefold()
    normalized_source_type = (source_type or "").strip().casefold()
    normalized_status = (status or "").strip().casefold()
    normalized_tag = (tag or "").strip().casefold()

    if normalized_keyword and normalized_keyword not in _item_search_text(item):
        return False
    if normalized_source_type and normalized_source_type not in {
        str(getattr(item.content_type, "value", item.content_type)).casefold(),
        (item.source_platform or "").casefold(),
    }:
        return False
    if normalized_status and str(getattr(item.status, "value", item.status)).casefold() != normalized_status:
        return False
    if normalized_tag:
        tags = {value.casefold() for value in _meta_list_values(item.raw_meta, "tags")}
        if normalized_tag not in tags:
            return False
    return True
