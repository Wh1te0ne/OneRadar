from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from app.db.models import (
    CollectionItem,
    ContentItem,
    ContentItemTag,
    ContentParsedDocument,
    ProcessingTask,
    Summary,
)
from app.db.models import (
    ReadingState as ReadingStateModel,
)
from app.db.models import (
    Transcript as TranscriptModel,
)
from app.db.session import SessionLocal
from app.schemas.annotations import HighlightEntry, NoteEntry
from app.schemas.common import ContentType, ItemStatus, ReadingState, TaskStatus
from app.schemas.items import (
    BilibiliPreviewResponse,
    ImportItemResponse,
    ItemDeleteResponse,
    ItemDetailResponse,
    ItemListEntry,
    ItemListResponse,
    ItemReprocessResponse,
    ParsedDocument,
    ReadingStateUpdateRequest,
    SummaryEntry,
    Transcript,
)
from app.schemas.organization import CollectionEntry, TagEntry
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

TRASH_RETENTION_DAYS = 7

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


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _deleted_at_from_meta(raw_meta: dict[str, object] | None) -> datetime | None:
    return _parse_datetime((raw_meta or {}).get("deleted_at"))


def _trash_expires_at(deleted_at: datetime | None) -> datetime | None:
    return deleted_at + timedelta(days=TRASH_RETENTION_DAYS) if deleted_at is not None else None


def _is_deleted_meta(raw_meta: dict[str, object] | None) -> bool:
    deleted_at = _deleted_at_from_meta(raw_meta)
    if deleted_at is None:
        return False
    expires_at = _trash_expires_at(deleted_at)
    return expires_at is None or expires_at > now_utc()


def _is_deleted_item(item: ContentItem) -> bool:
    return _is_deleted_meta(item.raw_meta or {})


def _is_expired_deleted_item(item: ContentItem) -> bool:
    deleted_at = _deleted_at_from_meta(item.raw_meta or {})
    expires_at = _trash_expires_at(deleted_at)
    return expires_at is not None and expires_at <= now_utc()


def _is_deleted_store_record(record: dict[str, object]) -> bool:
    deleted_at = _parse_datetime(record.get("deleted_at"))
    expires_at = _trash_expires_at(deleted_at)
    return deleted_at is not None and (expires_at is None or expires_at > now_utc())


def _is_expired_deleted_store_record(record: dict[str, object]) -> bool:
    deleted_at = _parse_datetime(record.get("deleted_at"))
    expires_at = _trash_expires_at(deleted_at)
    return expires_at is not None and expires_at <= now_utc()


def _remove_audio_artifact(raw_meta: dict[str, object] | None) -> None:
    podcast_meta = (raw_meta or {}).get("podcast")
    if not isinstance(podcast_meta, dict):
        return
    storage_path = podcast_meta.get("audio_storage_path")
    if not isinstance(storage_path, str) or not storage_path.strip():
        return
    try:
        Path(storage_path).unlink(missing_ok=True)
    except OSError:
        pass


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned or None


def _plain_text_blocks(value: str) -> list[dict[str, object]]:
    return [
        {"type": "paragraph", "text": block.strip()}
        for block in re.split(r"\n{2,}", value)
        if block.strip()
    ]


def _preview_parsed_document(
    parsed_text: str | None,
    parser_name: str | None,
    parser_version: str | None,
) -> dict[str, object] | None:
    text = (parsed_text or "").strip()
    if not text:
        return None
    return {
        "plain_text": text,
        "structured_blocks": _plain_text_blocks(text),
        "parser_name": _clean_optional_text(parser_name) or "feed-preview",
        "parser_version": _clean_optional_text(parser_version) or "v1",
    }

BILIBILI_BVID_RE = re.compile(r"(BV[0-9A-Za-z]{10,})")
BILIBILI_AV_RE = re.compile(r"(?:/video/|^)av(\d+)", re.IGNORECASE)


def _https_url(value: object) -> str | None:
    if not value:
        return None
    url = str(value)
    if url.startswith("http://"):
        return "https://" + url.removeprefix("http://")
    return url


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


def find_saved_item_for_url(url: str) -> dict[str, str] | None:
    normalized_url = normalize_source_url(url)
    if not normalized_url:
        return None

    try:
        validate_public_http_url(normalized_url)
    except ValueError:
        return None

    try:
        with SessionLocal() as session:
            item = session.execute(
                select(ContentItem).where(
                    or_(
                        ContentItem.normalized_url == normalized_url,
                        ContentItem.source_url == normalized_url,
                    )
                )
            ).scalars().first()
            if item is None:
                return None
            return {"item_id": str(item.id), "uid": str(item.id)}
    except SQLAlchemyError:
        existing = next(
            (
                item
                for item in STORE.items.values()
                if str(item.get("source_url", "")) == normalized_url
                or str(item.get("normalized_url", "")) == normalized_url
            ),
            None,
        )
        if existing is None:
            return None
        return {"item_id": str(existing["id"]), "uid": str(existing["id"])}


def _normalize_content_type(source_hint: str | None, url: str) -> ContentType:
    normalized_hint = (source_hint or "").strip().casefold()
    normalized_url = url.casefold()
    if normalized_hint in {"bilibili", "bilibili_video"} or any(
        host in normalized_url
        for host in ("bilibili.com", "b23.tv", "bili22.cn", "bili23.cn", "bili2233.cn")
    ):
        return ContentType.bilibili_video
    return ContentType.article


def _source_platform(content_type: ContentType) -> str:
    return "bilibili" if content_type == ContentType.bilibili_video else "web"


def _duration_text(seconds: int | None) -> str | None:
    if seconds is None or seconds < 0:
        return None
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _extract_bilibili_ref(url: str) -> tuple[str, str, str]:
    normalized_url = normalize_source_url(url)
    if not normalized_url:
        raise ValueError("url is required")
    validate_public_http_url(normalized_url)
    parsed = urlsplit(normalized_url)
    host = parsed.hostname.casefold() if parsed.hostname else ""
    if not any(domain in host for domain in ("bilibili.com", "b23.tv", "bili22.cn", "bili23.cn", "bili2233.cn")):
        raise ValueError("仅支持 Bilibili 视频链接")

    bvid_match = BILIBILI_BVID_RE.search(normalized_url)
    if bvid_match:
        bvid = bvid_match.group(1)
        return bvid, "bvid", f"https://www.bilibili.com/video/{bvid}/"

    av_match = BILIBILI_AV_RE.search(normalized_url)
    if av_match:
        aid = av_match.group(1)
        return aid, "aid", f"https://www.bilibili.com/video/av{aid}/"

    raise ValueError("没有识别到 BV 号或 av 号")


def _fetch_bilibili_view_payload(video_id: str, id_type: str) -> dict[str, object]:
    query_key = "bvid" if id_type == "bvid" else "aid"
    request = Request(
        f"https://api.bilibili.com/x/web-interface/view?{query_key}={video_id}",
        headers={
            "User-Agent": "OneRadar/0.1 (+https://localhost)",
            "Referer": "https://www.bilibili.com/",
        },
    )
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_bilibili_cover(url: str) -> tuple[bytes, str]:
    cover_url = _https_url(url)
    if not cover_url:
        raise ValueError("cover url is required")
    validate_public_http_url(cover_url)
    host = (urlsplit(cover_url).hostname or "").casefold()
    if host != "hdslb.com" and not host.endswith(".hdslb.com"):
        raise ValueError("仅支持 Bilibili 封面图片")

    request = Request(
        cover_url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.bilibili.com/",
        },
    )
    try:
        with urlopen(request, timeout=10) as response:
            content_type = response.headers.get_content_type() or "image/jpeg"
            if not content_type.startswith("image/"):
                raise ValueError("Bilibili 封面返回了非图片内容")
            return response.read(), content_type
    except HTTPError as exc:
        raise ValueError(f"Bilibili 封面获取失败：{exc.code}") from exc
    except URLError as exc:
        raise ValueError("Bilibili 封面获取失败") from exc


def _as_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _published_at_from_timestamp(value: object) -> datetime | None:
    timestamp = _as_int(value)
    if timestamp is None or timestamp <= 0:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def preview_bilibili_item(url: str) -> BilibiliPreviewResponse:
    video_id, id_type, canonical_url = _extract_bilibili_ref(url)
    payload = _fetch_bilibili_view_payload(video_id, id_type)
    if _as_int(payload.get("code")) != 0:
        message = str(payload.get("message") or payload.get("msg") or "Bilibili 视频信息获取失败")
        raise ValueError(message)

    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("Bilibili 视频信息为空")

    pages = data.get("pages")
    page_count = len(pages) if isinstance(pages, list) else None
    first_page = pages[0] if isinstance(pages, list) and pages and isinstance(pages[0], dict) else {}
    owner = data.get("owner") if isinstance(data.get("owner"), dict) else {}
    duration_seconds = _as_int(data.get("duration"))
    aid = _as_int(data.get("aid"))
    cid = _as_int(first_page.get("cid")) or _as_int(data.get("cid"))

    return BilibiliPreviewResponse(
        source_url=normalize_source_url(url),
        normalized_url=canonical_url,
        title=str(data.get("title") or "未命名视频"),
        owner_name=str(owner.get("name")) if owner.get("name") else None,
        owner_id=_as_int(owner.get("mid")),
        cover_url=_https_url(data.get("pic")),
        description=str(data.get("desc")) if data.get("desc") else None,
        duration_seconds=duration_seconds,
        duration_text=_duration_text(duration_seconds),
        published_at=_published_at_from_timestamp(data.get("pubdate")),
        bvid=str(data.get("bvid") or video_id) if id_type == "bvid" or data.get("bvid") else None,
        aid=aid,
        cid=cid,
        page_count=page_count,
        page_title=str(first_page.get("part")) if first_page.get("part") else None,
    )


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
        "podcast": raw_meta.get("podcast"),
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
    return max(
        transcripts,
        key=lambda record: (record.created_at, record.updated_at, str(record.id)),
    )


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
    return sorted(
        records,
        key=lambda record: (record.summary_type, record.version, record.created_at, str(record.id)),
    )


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
    records = list(item.highlights or [])
    if records:
        return [
            HighlightEntry(
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
            ).model_dump()
            for record in sorted(
                records,
                key=lambda entry: (entry.created_at, str(entry.id)),
                reverse=True,
            )
        ]
    raw_meta = item.raw_meta or {}
    return [
        {**highlight, "item_id": str(item.id)}
        for highlight in list(raw_meta.get("highlights") or [])
    ]


def _item_notes(item: ContentItem) -> list[dict[str, object]]:
    records = list(item.notes or [])
    if records:
        return [
            NoteEntry(
                id=str(record.id),
                item_id=str(record.content_item_id),
                content=record.content,
                highlight_id=str(record.highlight_id) if record.highlight_id else None,
                created_at=record.created_at,
                updated_at=record.updated_at,
            ).model_dump()
            for record in sorted(
                records,
                key=lambda entry: (entry.created_at, str(entry.id)),
                reverse=True,
            )
        ]
    raw_meta = item.raw_meta or {}
    return [{**note, "item_id": str(item.id)} for note in list(raw_meta.get("notes") or [])]


def _item_tags(item: ContentItem) -> list[TagEntry]:
    item_tags = list(item.item_tags or [])
    if item_tags:
        return [
            TagEntry(id=link.tag.normalized_name, name=link.tag.name)
            for link in sorted(item_tags, key=lambda entry: entry.tag.name.casefold())
            if link.tag is not None
        ]
    raw_meta = item.raw_meta or {}
    tags = raw_meta.get("tags") or []
    return [TagEntry(id=str(tag).strip().casefold(), name=str(tag)) for tag in tags]


def _item_collections(item: ContentItem) -> list[CollectionEntry]:
    memberships = list(item.collection_items or [])
    if memberships:
        return [
            CollectionEntry(id=str(link.collection.id), name=link.collection.name)
            for link in sorted(memberships, key=lambda entry: entry.collection.name.casefold())
            if link.collection is not None
        ]
    raw_meta = item.raw_meta or {}
    return [CollectionEntry(**collection) for collection in list(raw_meta.get("collections") or [])]


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
    summary_text = " ".join(
        summary.content.strip() for summary in summaries if summary.content.strip()
    )
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
    item_tags = list(item.item_tags or [])
    if item_tags:
        return [link.tag.name for link in item_tags if link.tag is not None]
    return _meta_list_values(item.raw_meta or {}, "tags")


def _item_list_entry(item: ContentItem) -> ItemListEntry:
    reading_state = _item_reading_state(item)
    folder_id, folder_name, is_inbox = _item_folder_info(item)
    deleted_at = _deleted_at_from_meta(item.raw_meta or {})
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
        progress_percent=reading_state.progress_percent,
        last_read_at=reading_state.last_read_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
        deleted_at=deleted_at,
        delete_expires_at=_trash_expires_at(deleted_at),
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


def _fallback_import(
    url: str,
    source_hint: str | None,
    *,
    title: str | None = None,
    site_title: str | None = None,
    author: str | None = None,
    published_at: datetime | None = None,
    summary: str | None = None,
    parsed_text: str | None = None,
    parser_name: str | None = None,
    parser_version: str | None = None,
    generate_summary: bool = False,
) -> ImportItemResponse:
    seed_store()
    normalized_url = normalize_source_url(url)
    if not normalized_url:
        raise ValueError("url is required")
    validate_public_http_url(normalized_url)
    content_type = _normalize_content_type(source_hint, normalized_url)

    with STORE.lock:
        existing = next(
            (item for item in STORE.items.values() if item["source_url"] == normalized_url),
            None,
        )
        if existing is not None:
            preview_document = _preview_parsed_document(parsed_text, parser_name, parser_version)
            initial_title = _clean_optional_text(title)
            initial_author = _clean_optional_text(author)
            initial_site = _clean_optional_text(site_title)
            if preview_document or initial_title or initial_author or initial_site or published_at:
                if initial_title:
                    existing["title"] = initial_title
                metadata = dict(existing.get("metadata") or {})
                if initial_author:
                    metadata["author_name"] = initial_author
                if initial_site:
                    metadata["site_name"] = initial_site
                if published_at:
                    metadata["published_at"] = published_at.isoformat()
                existing["metadata"] = metadata
                if preview_document:
                    existing["parsed_document"] = preview_document
                    existing["status"] = ItemStatus.completed.value
            if preview_document and generate_summary:
                task_id = str(uuid4())
                STORE.tasks[task_id] = {
                    "id": task_id,
                    "item_id": str(existing["id"]),
                    "task_type": "generate_summary",
                    "status": "pending",
                    "attempt_count": 0,
                    "error_message": None,
                    "created_at": now_utc(),
                }
            else:
                task_id = None
            folder_id = str(existing.get("folder_id", INBOX_FOLDER_ID))
            folder_name = str(existing.get("folder_name", INBOX_FOLDER_NAME))
            return ImportItemResponse(
                uid=str(existing["id"]),
                item_id=str(existing["id"]),
                existing_uid=str(existing["id"]),
                task_id=task_id,
                status="pending" if task_id else "already_exists",
                content_type=existing["content_type"],
                folder_id=folder_id,
                folder_name=folder_name,
                is_duplicate=True,
            )

        item_id = str(uuid4())
        task_id = str(uuid4())
        preview_document = _preview_parsed_document(parsed_text, parser_name, parser_version)
        initial_title = _clean_optional_text(title) or "新导入内容"
        published_iso = published_at.isoformat() if published_at else None
        item_record = {
            "id": item_id,
            "uid": item_id,
            "title": initial_title,
            "content_type": content_type,
            "source_url": normalized_url,
            "folder_id": INBOX_FOLDER_ID,
            "folder_name": INBOX_FOLDER_NAME,
            "is_inbox": True,
            "status": ItemStatus.completed.value if preview_document else ItemStatus.pending.value,
            "metadata": {
                "author_name": _clean_optional_text(author),
                "published_at": published_iso,
                "site_name": _clean_optional_text(site_title),
            },
            "parsed_document": preview_document or {
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
        if summary:
            item_record["summaries"] = [
                {
                    "summary_type": "one_line",
                    "content": summary,
                    "model_name": None,
                    "version": 1,
                }
            ]
        STORE.items[item_id] = item_record
        if preview_document:
            if generate_summary:
                STORE.tasks[task_id] = {
                    "id": task_id,
                    "item_id": item_id,
                    "task_type": "generate_summary",
                    "status": "pending",
                    "attempt_count": 0,
                    "error_message": None,
                    "created_at": now_utc(),
                }
            else:
                task_id = None
        else:
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


def import_item(
    url: str,
    source_hint: str | None,
    *,
    title: str | None = None,
    site_title: str | None = None,
    author: str | None = None,
    published_at: datetime | None = None,
    summary: str | None = None,
    parsed_text: str | None = None,
    parser_name: str | None = None,
    parser_version: str | None = None,
    generate_summary: bool = False,
) -> ImportItemResponse:
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
            preview_document = _preview_parsed_document(parsed_text, parser_name, parser_version)
            initial_title = _clean_optional_text(title) or "新导入内容"
            initial_author = _clean_optional_text(author)
            initial_site = _clean_optional_text(site_title)
            initial_summary = _clean_optional_text(summary)

            existing = session.execute(
                select(ContentItem).where(
                    ContentItem.user_id == user.id,
                    ContentItem.normalized_url == normalized_url,
                )
            ).scalar_one_or_none()
            if existing is not None:
                task: ProcessingTask | None = None
                if preview_document or initial_title or initial_author or initial_site or published_at:
                    if initial_title:
                        existing.title = initial_title
                    if initial_author:
                        existing.author_name = initial_author
                    if published_at:
                        existing.published_at = published_at
                    raw_meta = dict(existing.raw_meta or {})
                    metadata = dict(raw_meta.get("metadata") or {})
                    if initial_author:
                        metadata["author_name"] = initial_author
                    if published_at:
                        metadata["published_at"] = published_at.isoformat()
                    if initial_site:
                        metadata["site_name"] = initial_site
                        raw_meta["site_name"] = initial_site
                    raw_meta["metadata"] = metadata
                    if preview_document:
                        raw_meta["parsed_document"] = preview_document
                        existing.status = ItemStatus.completed.value
                        parser_key = str(preview_document["parser_name"])
                        parser_version_key = str(preview_document["parser_version"])
                        existing_document = session.execute(
                            select(ContentParsedDocument).where(
                                ContentParsedDocument.content_item_id == existing.id,
                                ContentParsedDocument.parser_name == parser_key,
                                ContentParsedDocument.parser_version == parser_version_key,
                            )
                        ).scalar_one_or_none()
                        if existing_document is None:
                            session.add(
                                ContentParsedDocument(
                                    content_item_id=existing.id,
                                    parser_name=parser_key,
                                    parser_version=parser_version_key,
                                    title=initial_title or existing.title,
                                    excerpt=initial_summary,
                                    byline=initial_author or existing.author_name,
                                    language=None,
                                    plain_text=str(preview_document["plain_text"]),
                                    structured_blocks=list(preview_document["structured_blocks"]),
                                    quality_score=None,
                                    source_snapshot_id=None,
                                )
                            )
                        else:
                            existing_document.title = initial_title or existing_document.title
                            existing_document.excerpt = initial_summary or existing_document.excerpt
                            existing_document.byline = initial_author or existing_document.byline
                            existing_document.plain_text = str(preview_document["plain_text"])
                            existing_document.structured_blocks = list(preview_document["structured_blocks"])
                    existing.raw_meta = raw_meta
                if preview_document and generate_summary:
                    task = ProcessingTask(
                        content_item_id=existing.id,
                        user_id=user.id,
                        task_type="generate_summary",
                        status=TaskStatus.pending.value,
                        priority=0,
                        attempt_count=0,
                        max_attempts=3,
                        locked_by=None,
                        payload={
                            "source_hint": source_hint,
                            "url": normalized_url,
                            "title": initial_title or existing.title,
                            "summary": initial_summary,
                            "parsed_document": preview_document,
                        },
                        result={},
                        error_message=None,
                        started_at=None,
                        finished_at=None,
                        next_retry_at=None,
                    )
                    session.add(task)
                session.commit()
                folder_id, folder_name, _ = _item_folder_info(existing)
                return ImportItemResponse(
                    uid=str(existing.id),
                    item_id=str(existing.id),
                    existing_uid=str(existing.id),
                    task_id=str(task.id) if task is not None else None,
                    status="pending" if task is not None else "already_exists",
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
                title=initial_title,
                subtitle=None,
                author_name=initial_author,
                author_id=None,
                cover_url=None,
                duration_seconds=None,
                language=None,
                published_at=published_at,
                status=ItemStatus.completed.value if preview_document else ItemStatus.pending.value,
                visibility="private",
                raw_meta={
                    "metadata": {
                        "author_name": initial_author,
                        "published_at": published_at.isoformat() if published_at else None,
                        "site_name": initial_site,
                    },
                    "site_name": initial_site,
                    "parsed_document": preview_document or DEFAULT_PARSED_DOCUMENT,
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

            if preview_document:
                session.add(
                    ContentParsedDocument(
                        content_item_id=item.id,
                        parser_name=str(preview_document["parser_name"]),
                        parser_version=str(preview_document["parser_version"]),
                        title=initial_title,
                        excerpt=initial_summary,
                        byline=initial_author,
                        language=None,
                        plain_text=str(preview_document["plain_text"]),
                        structured_blocks=list(preview_document["structured_blocks"]),
                        quality_score=None,
                        source_snapshot_id=None,
                    )
                )

            task: ProcessingTask | None = None
            if preview_document and generate_summary:
                task = ProcessingTask(
                    content_item_id=item.id,
                    user_id=user.id,
                    task_type="generate_summary",
                    status=TaskStatus.pending.value,
                    priority=0,
                    attempt_count=0,
                    max_attempts=3,
                    locked_by=None,
                    payload={
                        "source_hint": source_hint,
                        "url": normalized_url,
                        "title": initial_title,
                        "summary": initial_summary,
                        "parsed_document": preview_document,
                    },
                    result={},
                    error_message=None,
                    started_at=None,
                    finished_at=None,
                    next_retry_at=None,
                )
                session.add(task)
            elif not preview_document:
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
                task_id=str(task.id) if task is not None else None,
                status="pending" if task is not None else "completed",
                content_type=content_type,
                folder_id=folder_id,
                folder_name=folder_name,
                is_duplicate=False,
            )
    except SQLAlchemyError:
        return _fallback_import(
            url,
            source_hint,
            title=title,
            site_title=site_title,
            author=author,
            published_at=published_at,
            summary=summary,
            parsed_text=parsed_text,
            parser_name=parser_name,
            parser_version=parser_version,
            generate_summary=generate_summary,
        )


def _filtered_items(
    records: list[ContentItem],
    folder_id: str | None,
    inbox_only: bool,
) -> list[ContentItem]:
    if folder_id is not None:
        target = normalize_folder_identifier(folder_id)
        if target == INBOX_FOLDER_ID:
            return [
                item
                for item in records
                if _item_folder_info(item)[2]
                or item.folder_id is None
                or _item_folder_info(item)[0] == INBOX_FOLDER_ID
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
    collection_id: str | None = None,
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
                        selectinload(ContentItem.item_tags).selectinload(ContentItemTag.tag),
                        selectinload(ContentItem.collection_items).selectinload(
                            CollectionItem.collection
                        ),
                        selectinload(ContentItem.reading_state),
                    )
                    .where(ContentItem.user_id == user.id)
                    .order_by(ContentItem.created_at.desc())
                ).scalars()
            )
            expired_deleted = [item for item in items if _is_expired_deleted_item(item)]
            for item in expired_deleted:
                _remove_audio_artifact(item.raw_meta)
                session.delete(item)
            if expired_deleted:
                session.commit()
                items = [item for item in items if item not in expired_deleted]

            items = [item for item in items if not _is_deleted_item(item)]
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
                    collection_id=collection_id,
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
        with STORE.lock:
            expired_ids = [
                str(item_id)
                for item_id, record in STORE.items.items()
                if _is_expired_deleted_store_record(record)
            ]
            for item_id in expired_ids:
                record = STORE.items.pop(item_id, None)
                if record is not None:
                    _remove_audio_artifact(record.get("raw_meta") if isinstance(record.get("raw_meta"), dict) else record)
            items = [
                record
                for record in STORE.items.values()
                if not _is_deleted_store_record(record)
            ]
        items = sorted(items, key=lambda record: record.get("updated_at") or record["created_at"], reverse=True)
        if folder_id is not None:
            target = normalize_folder_identifier(folder_id)
            if target == INBOX_FOLDER_ID:
                items = [
                    record
                    for record in items
                    if bool(record.get("is_inbox", False))
                    or str(record.get("folder_id", INBOX_FOLDER_ID)) == INBOX_FOLDER_ID
                ]
            else:
                items = [
                    record
                    for record in items
                    if str(record.get("folder_id", INBOX_FOLDER_ID)) == target
                ]
        elif inbox_only:
            items = [
                record
                for record in items
                if bool(record.get("is_inbox", False)) or record.get("folder_id") is None
            ]

        normalized_keyword = (keyword or "").strip().casefold()
        normalized_source_type = (source_type or "").strip().casefold()
        normalized_status = (status or "").strip().casefold()
        normalized_tag = (tag or "").strip().casefold()
        normalized_collection_id = (collection_id or "").strip()

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
                    str(
                        getattr(
                            record.get("content_type", ""),
                            "value",
                            record.get("content_type", ""),
                        )
                    ).casefold(),
                    (
                        "bilibili"
                        if record.get("content_type") == ContentType.bilibili_video
                        else "web"
                    ),
                }
            ]
        if normalized_status:
            items = [
                record
                for record in items
                if str(
                    getattr(record.get("status", ""), "value", record.get("status", ""))
                ).casefold()
                == normalized_status
            ]
        if normalized_tag:
            items = [
                record
                for record in items
                if normalized_tag
                in {str(tag_value).casefold() for tag_value in record.get("tags", [])}
            ]
        if normalized_collection_id:
            collection = STORE.collections.get(normalized_collection_id)
            item_ids = set(collection.get("item_ids", []) if collection else [])
            items = [record for record in items if str(record.get("id")) in item_ids]

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
                    progress_percent=float(record["reading_state"].get("progress_percent", 0) or 0),
                    last_read_at=record["reading_state"].get("last_read_at"),
                    created_at=record["created_at"],
                    updated_at=record["updated_at"],
                    deleted_at=_parse_datetime(record.get("deleted_at")),
                    delete_expires_at=_trash_expires_at(_parse_datetime(record.get("deleted_at"))),
                    summary=(
                        str(record.get("parsed_document", {}).get("excerpt", "")).strip()
                        or None
                    ),
                    tags=[
                        str(tag_value)
                        for tag_value in record.get("tags", [])
                        if str(tag_value).strip()
                    ],
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
                    selectinload(ContentItem.highlights),
                    selectinload(ContentItem.notes),
                    selectinload(ContentItem.item_tags).selectinload(ContentItemTag.tag),
                    selectinload(ContentItem.collection_items).selectinload(CollectionItem.collection),
                    selectinload(ContentItem.reading_state),
                )
                .where(ContentItem.id == UUID(item_id))
            ).scalar_one_or_none()
            if item is not None:
                if _is_expired_deleted_item(item):
                    _remove_audio_artifact(item.raw_meta)
                    session.delete(item)
                    session.commit()
                    raise ValueError("item not found")
                if _is_deleted_item(item):
                    raise ValueError("item not found")
                return _item_detail_response(item)
    except (SQLAlchemyError, ValueError):
        pass

    seed_store()
    record = STORE.items.get(item_id)
    if record is not None and _is_expired_deleted_store_record(record):
        with STORE.lock:
            expired_record = STORE.items.pop(item_id, None)
        if expired_record is not None:
            _remove_audio_artifact(expired_record.get("raw_meta") if isinstance(expired_record.get("raw_meta"), dict) else expired_record)
        record = None
    if record is None or _is_deleted_store_record(record):
        raise ValueError("item not found")
    folder_id = str(record.get("folder_id", INBOX_FOLDER_ID))
    folder_name = str(record.get("folder_name", INBOX_FOLDER_NAME))
    is_inbox = bool(record.get("is_inbox", folder_id == INBOX_FOLDER_ID))
    collections = [
        {
            "id": str(collection["id"]),
            "name": str(collection["name"]),
        }
        for collection in STORE.collections.values()
        if item_id in set(collection.get("item_ids", []) or [])
    ]
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
        tags=[
            TagEntry(id=str(tag).strip().casefold(), name=str(tag))
            for tag in record["tags"]
        ],
        collections=[CollectionEntry(**collection) for collection in collections],
        reading_state=ReadingState.model_validate(record["reading_state"]),
    )


def update_reading_state(item_id: str, payload: ReadingStateUpdateRequest) -> ReadingState:
    item_uuid: UUID | None
    try:
        item_uuid = UUID(item_id)
    except ValueError:
        item_uuid = None

    if item_uuid is not None:
        try:
            with SessionLocal() as session:
                user = get_primary_user(session)
                item = session.execute(
                    select(ContentItem)
                    .options(selectinload(ContentItem.reading_state))
                    .where(
                        ContentItem.user_id == user.id,
                        ContentItem.id == item_uuid,
                    )
                ).scalar_one_or_none()
                if item is None:
                    raise ValueError("item not found")

                raw_meta = dict(item.raw_meta or {})
                fallback_state = (
                    raw_meta.get("reading_state")
                    if isinstance(raw_meta.get("reading_state"), dict)
                    else {}
                )
                fallback_state = dict(DEFAULT_READING_STATE) | dict(fallback_state)

                reading_state_record = item.reading_state
                if reading_state_record is None:
                    reading_state_record = ReadingStateModel(
                        user_id=user.id,
                        content_item_id=item.id,
                        is_read=False,
                        progress_percent=float(fallback_state.get("progress_percent", 0) or 0),
                        last_read_at=None,
                        is_archived=bool(fallback_state.get("is_archived", False)),
                    )
                    session.add(reading_state_record)
                    session.flush()

                next_progress = float(
                    payload.progress_percent
                    if payload.progress_percent is not None
                    else reading_state_record.progress_percent
                )
                next_archived = bool(
                    payload.is_archived
                    if payload.is_archived is not None
                    else reading_state_record.is_archived
                )
                next_favorited = bool(
                    payload.is_favorited
                    if payload.is_favorited is not None
                    else fallback_state.get("is_favorited", False)
                )
                next_last_read_at = payload.last_read_at or now_utc()

                reading_state_record.progress_percent = next_progress
                reading_state_record.is_read = next_progress >= 100
                reading_state_record.is_archived = next_archived
                reading_state_record.last_read_at = next_last_read_at
                if payload.last_position_type is not None:
                    reading_state_record.last_position_type = payload.last_position_type
                if payload.last_position_value is not None:
                    reading_state_record.last_position_value = payload.last_position_value

                raw_meta["reading_state"] = {
                    **fallback_state,
                    "progress_percent": next_progress,
                    "last_read_at": (
                        next_last_read_at.isoformat() if next_last_read_at is not None else None
                    ),
                    "is_archived": next_archived,
                    "is_favorited": next_favorited,
                    "last_position_type": (
                        payload.last_position_type
                        if payload.last_position_type is not None
                        else reading_state_record.last_position_type
                    ),
                    "last_position_value": (
                        payload.last_position_value
                        if payload.last_position_value is not None
                        else reading_state_record.last_position_value
                    ),
                }
                item.raw_meta = raw_meta
                session.commit()

                return ReadingState(
                    progress_percent=next_progress,
                    last_read_at=next_last_read_at,
                    is_archived=next_archived,
                    is_favorited=next_favorited,
                )
        except SQLAlchemyError:
            pass

    seed_store()
    with STORE.lock:
        record = STORE.items.get(item_id)
        if record is None:
            raise ValueError("item not found")

        reading_state = dict(DEFAULT_READING_STATE)
        reading_state.update(record.get("reading_state") or {})
        if payload.progress_percent is not None:
            reading_state["progress_percent"] = float(payload.progress_percent)
        if payload.is_archived is not None:
            reading_state["is_archived"] = bool(payload.is_archived)
        if payload.is_favorited is not None:
            reading_state["is_favorited"] = bool(payload.is_favorited)
        if payload.last_position_type is not None:
            reading_state["last_position_type"] = payload.last_position_type
        if payload.last_position_value is not None:
            reading_state["last_position_value"] = payload.last_position_value

        next_last_read_at = payload.last_read_at or now_utc()
        reading_state["last_read_at"] = next_last_read_at
        record["reading_state"] = reading_state
        record["updated_at"] = next_last_read_at
        return ReadingState.model_validate(reading_state)


def delete_item(item_id: str) -> ItemDeleteResponse:
    try:
        with SessionLocal() as session:
            item = session.get(ContentItem, UUID(item_id))
            if item is None:
                raise ValueError("item not found")
            deleted_at = now_utc()
            item.raw_meta = {
                **(item.raw_meta or {}),
                "deleted_at": deleted_at.isoformat(),
            }
            session.commit()
            return ItemDeleteResponse(uid=str(item.id), deleted=True)
    except (SQLAlchemyError, ValueError) as exc:
        seed_store()
        with STORE.lock:
            record = STORE.items.get(item_id)
            if record is not None:
                record["deleted_at"] = now_utc()
                record["updated_at"] = now_utc()
        if record is None:
            raise ValueError("item not found") from exc
        return ItemDeleteResponse(uid=item_id, deleted=True)


def list_deleted_items(page: int, page_size: int) -> ItemListResponse:
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
                        selectinload(ContentItem.item_tags).selectinload(ContentItemTag.tag),
                        selectinload(ContentItem.reading_state),
                    )
                    .where(ContentItem.user_id == user.id)
                    .order_by(ContentItem.updated_at.desc())
                ).scalars()
            )
            expired_deleted = [item for item in items if _is_expired_deleted_item(item)]
            for item in expired_deleted:
                _remove_audio_artifact(item.raw_meta)
                session.delete(item)
            if expired_deleted:
                session.commit()
                items = [item for item in items if item not in expired_deleted]
            items = [item for item in items if _is_deleted_item(item)]
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
        with STORE.lock:
            expired_ids = [
                str(item_id)
                for item_id, record in STORE.items.items()
                if _is_expired_deleted_store_record(record)
            ]
            for item_id in expired_ids:
                record = STORE.items.pop(item_id, None)
                if record is not None:
                    _remove_audio_artifact(record.get("raw_meta") if isinstance(record.get("raw_meta"), dict) else record)
            items = [
                record
                for record in STORE.items.values()
                if _is_deleted_store_record(record)
            ]
        items = sorted(items, key=lambda record: record.get("updated_at") or record.get("created_at"), reverse=True)
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
                    progress_percent=float(record["reading_state"].get("progress_percent", 0) or 0),
                    last_read_at=record["reading_state"].get("last_read_at"),
                    created_at=record["created_at"],
                    updated_at=record["updated_at"],
                    deleted_at=_parse_datetime(record.get("deleted_at")),
                    delete_expires_at=_trash_expires_at(_parse_datetime(record.get("deleted_at"))),
                    summary=str(record.get("parsed_document", {}).get("excerpt", "")).strip() or None,
                    tags=[str(tag_value) for tag_value in record.get("tags", []) if str(tag_value).strip()],
                )
                for record in items[start:end]
            ],
            page=page,
            page_size=page_size,
            total=len(items),
        )


def restore_item(item_id: str) -> ItemDeleteResponse:
    try:
        with SessionLocal() as session:
            item = session.get(ContentItem, UUID(item_id))
            if item is None or not _is_deleted_item(item):
                raise ValueError("item not found")
            raw_meta = dict(item.raw_meta or {})
            raw_meta.pop("deleted_at", None)
            item.raw_meta = raw_meta
            session.commit()
            return ItemDeleteResponse(uid=str(item.id), deleted=False)
    except (SQLAlchemyError, ValueError) as exc:
        seed_store()
        with STORE.lock:
            record = STORE.items.get(item_id)
            if record is None or not _is_deleted_store_record(record):
                raise ValueError("item not found") from exc
            record.pop("deleted_at", None)
            record["updated_at"] = now_utc()
        return ItemDeleteResponse(uid=item_id, deleted=False)


def purge_item(item_id: str) -> ItemDeleteResponse:
    try:
        with SessionLocal() as session:
            item = session.get(ContentItem, UUID(item_id))
            if item is None:
                raise ValueError("item not found")
            _remove_audio_artifact(item.raw_meta)
            session.delete(item)
            session.commit()
            return ItemDeleteResponse(uid=str(item.id), deleted=True)
    except (SQLAlchemyError, ValueError) as exc:
        seed_store()
        with STORE.lock:
            record = STORE.items.pop(item_id, None)
        if record is None:
            raise ValueError("item not found") from exc
        _remove_audio_artifact(record.get("raw_meta") if isinstance(record.get("raw_meta"), dict) else record)
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


def generate_item_summary(item_id: str) -> ItemReprocessResponse:
    try:
        with SessionLocal() as session:
            user = get_primary_user(session)
            item = session.get(ContentItem, UUID(item_id))
            if item is None:
                raise ValueError("item not found")
            existing_task = session.execute(
                select(ProcessingTask)
                .where(
                    ProcessingTask.content_item_id == item.id,
                    ProcessingTask.task_type == "generate_summary",
                    ProcessingTask.status.in_(
                        [
                            TaskStatus.pending.value,
                            TaskStatus.running.value,
                            TaskStatus.retrying.value,
                        ]
                    ),
                )
                .order_by(ProcessingTask.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if existing_task is not None:
                return ItemReprocessResponse(
                    item_id=item_id,
                    task_id=str(existing_task.id),
                    status=existing_task.status,
                )
            task = ProcessingTask(
                content_item_id=item.id,
                user_id=user.id,
                task_type="generate_summary",
                status=TaskStatus.pending.value,
                priority=0,
                attempt_count=0,
                max_attempts=3,
                locked_by=None,
                payload={"steps": ["summarize"]},
                result={},
                error_message=None,
                started_at=None,
                finished_at=None,
                next_retry_at=None,
            )
            session.add(task)
            session.commit()
            return ItemReprocessResponse(item_id=item_id, task_id=str(task.id), status="pending")
    except (SQLAlchemyError, ValueError) as exc:
        seed_store()
        with STORE.lock:
            if item_id not in STORE.items:
                raise ValueError("item not found") from exc
            for task in STORE.tasks.values():
                if (
                    str(task.get("item_id")) == item_id
                    and str(task.get("task_type")) == "generate_summary"
                    and str(task.get("status")) in {"pending", "running", "retrying"}
                ):
                    return ItemReprocessResponse(
                        item_id=item_id,
                        task_id=str(task["id"]),
                        status=str(task["status"]),
                    )
            task_id = str(uuid4())
            STORE.tasks[task_id] = {
                "id": task_id,
                "item_id": item_id,
                "task_type": "generate_summary",
                "status": TaskStatus.pending.value,
                "attempt_count": 0,
                "error_message": None,
                "created_at": now_utc(),
                "payload": {"steps": ["summarize"]},
            }
        return ItemReprocessResponse(item_id=item_id, task_id=task_id, status="pending")


def _matches_item_filters(
    item: ContentItem,
    *,
    keyword: str | None,
    source_type: str | None,
    status: str | None,
    tag: str | None,
    collection_id: str | None,
) -> bool:
    normalized_keyword = (keyword or "").strip().casefold()
    normalized_source_type = (source_type or "").strip().casefold()
    normalized_status = (status or "").strip().casefold()
    normalized_tag = (tag or "").strip().casefold()
    normalized_collection_id = (collection_id or "").strip()

    if normalized_keyword and normalized_keyword not in _item_search_text(item):
        return False
    if normalized_source_type and normalized_source_type not in {
        str(getattr(item.content_type, "value", item.content_type)).casefold(),
        (item.source_platform or "").casefold(),
    }:
        return False
    if (
        normalized_status
        and str(getattr(item.status, "value", item.status)).casefold() != normalized_status
    ):
        return False
    if normalized_tag:
        tags = {entry.name.casefold() for entry in _item_tags(item)}
        if normalized_tag not in tags:
            return False
    if normalized_collection_id:
        collections = {entry.id for entry in _item_collections(item)}
        if normalized_collection_id not in collections:
            return False
    return True
