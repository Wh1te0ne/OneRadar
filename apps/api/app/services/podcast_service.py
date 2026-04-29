from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from hashlib import sha256
from html import unescape
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4
from xml.etree import ElementTree as ET

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import ContentItem, IntegrationSetting, ProcessingTask
from app.db.session import SessionLocal
from app.schemas.common import ContentType, ItemStatus, TaskStatus
from app.schemas.podcasts import (
    PodcastEpisodeFeedEntry,
    PodcastEpisodeImportRequest,
    PodcastEpisodeImportResponse,
    PodcastSearchItem,
    PodcastSearchResponse,
    PodcastSubscriptionCreateRequest,
    PodcastSubscriptionDeleteResponse,
    PodcastSubscriptionEntry,
    PodcastSubscriptionListResponse,
)
from app.services.db_access import get_primary_user
from app.services.feed_service import _parse_datetime, _read_feed_xml
from app.services.folders_service import (
    INBOX_FOLDER_ID,
    INBOX_FOLDER_NAME,
    build_folder_meta,
    resolve_folder,
)
from app.services.items_service import DEFAULT_PARSED_DOCUMENT, DEFAULT_READING_STATE
from app.services.store import STORE, now_utc, seed_store
from app.services.url_safety import validate_public_http_url

PODCASTS_INTEGRATION_KEY = "podcasts"
PODCASTS_DISPLAY_NAME = "Podcasts"
APPLE_SEARCH_URL = "https://itunes.apple.com/search"
DEFAULT_COUNTRY = "US"
DEFAULT_SEARCH_LIMIT = 12
MAX_SEARCH_LIMIT = 25
DEFAULT_EPISODE_LIMIT = 80
MAX_EPISODE_LIMIT = 200


def _normalize_whitespace(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"\s+", " ", value).strip()
    return normalized or None


def _strip_html(value: str | None) -> str | None:
    if value is None:
        return None
    text = re.sub(r"<[^>]+>", " ", value)
    return _normalize_whitespace(unescape(text))


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(node: ET.Element, *names: str) -> str | None:
    for child in node:
        if _local_name(child.tag) in names and child.text and child.text.strip():
            return child.text.strip()
    return None


def _first_child(node: ET.Element, *names: str) -> ET.Element | None:
    for child in node:
        if _local_name(child.tag) in names:
            return child
    return None


def _parse_duration_seconds(value: str | None) -> int | None:
    normalized = _normalize_whitespace(value)
    if not normalized:
        return None
    if normalized.isdigit():
        return int(normalized)
    parts = normalized.split(":")
    try:
        if len(parts) == 2:
            minutes, seconds = parts
            return int(minutes) * 60 + int(seconds)
        if len(parts) == 3:
            hours, minutes, seconds = parts
            return int(hours) * 3600 + int(minutes) * 60 + int(seconds)
    except ValueError:
        return None
    return None


def _stable_id(*parts: str | None) -> str:
    joined = "\n".join(part or "" for part in parts)
    return sha256(joined.encode("utf-8")).hexdigest()


def _episode_identity(
    feed_url: str,
    guid: str | None,
    enclosure_url: str | None,
    title: str,
    published_at: datetime | None,
) -> str:
    source = guid or enclosure_url or f"{title}:{published_at.isoformat() if published_at else ''}"
    return "podcast-episode:" + _stable_id(feed_url, source)


def _subscription_id(feed_url: str) -> str:
    return "podcast-feed:" + _stable_id(feed_url)[:24]


def _search_apple_podcasts(query: str, country: str, limit: int) -> list[dict[str, object]]:
    params = urlencode(
        {
            "media": "podcast",
            "entity": "podcast",
            "country": country,
            "limit": str(limit),
            "term": query,
        }
    )
    request = Request(
        f"{APPLE_SEARCH_URL}?{params}",
        headers={
            "Accept": "application/json",
            "User-Agent": "OneRadarAPI/0.1",
        },
    )
    with urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    results = payload.get("results") if isinstance(payload, dict) else None
    return [entry for entry in results or [] if isinstance(entry, dict)]


def search_podcasts(
    query: str,
    country: str = DEFAULT_COUNTRY,
    limit: int = DEFAULT_SEARCH_LIMIT,
) -> PodcastSearchResponse:
    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("search query is required")
    normalized_country = (country or DEFAULT_COUNTRY).strip().upper()[:2] or DEFAULT_COUNTRY
    normalized_limit = max(1, min(limit, MAX_SEARCH_LIMIT))
    results = _search_apple_podcasts(normalized_query, normalized_country, normalized_limit)
    items: list[PodcastSearchItem] = []
    for entry in results:
        feed_url = _normalize_whitespace(str(entry.get("feedUrl") or "")) or None
        items.append(
            PodcastSearchItem(
                itunes_id=(
                    str(entry.get("collectionId") or entry.get("trackId") or "").strip()
                    or None
                ),
                title=str(entry.get("collectionName") or entry.get("trackName") or "未命名播客"),
                author=_normalize_whitespace(str(entry.get("artistName") or "")) or None,
                feed_url=feed_url,
                page_url=_normalize_whitespace(
                    str(entry.get("collectionViewUrl") or entry.get("trackViewUrl") or "")
                )
                or None,
                image_url=_normalize_whitespace(
                    str(entry.get("artworkUrl600") or entry.get("artworkUrl100") or "")
                )
                or None,
                genre=_normalize_whitespace(str(entry.get("primaryGenreName") or "")) or None,
                episode_count=(
                    int(entry["trackCount"]) if isinstance(entry.get("trackCount"), int) else None
                ),
                is_subscribable=bool(feed_url),
            )
        )
    return PodcastSearchResponse(items=items)


def _integration_subscriptions(config: dict[str, object]) -> list[dict[str, object]]:
    subscriptions = config.get("subscriptions")
    return [dict(entry) for entry in subscriptions or [] if isinstance(entry, dict)]


def _subscription_entry(record: dict[str, object]) -> PodcastSubscriptionEntry:
    created_at = record.get("created_at")
    updated_at = record.get("updated_at")
    return PodcastSubscriptionEntry(
        id=str(record["id"]),
        feed_url=str(record["feed_url"]),
        title=str(record["title"]),
        author=str(record["author"]) if record.get("author") else None,
        image_url=str(record["image_url"]) if record.get("image_url") else None,
        itunes_id=str(record["itunes_id"]) if record.get("itunes_id") else None,
        page_url=str(record["page_url"]) if record.get("page_url") else None,
        created_at=(
            created_at
            if isinstance(created_at, datetime)
            else _parse_datetime(str(created_at)) or now_utc()
        ),
        updated_at=(
            updated_at
            if isinstance(updated_at, datetime)
            else _parse_datetime(str(updated_at)) or now_utc()
        ),
    )


def _serialize_subscription(entry: PodcastSubscriptionEntry) -> dict[str, object]:
    return {
        "id": entry.id,
        "feed_url": entry.feed_url,
        "title": entry.title,
        "author": entry.author,
        "image_url": entry.image_url,
        "itunes_id": entry.itunes_id,
        "page_url": entry.page_url,
        "created_at": entry.created_at.isoformat(),
        "updated_at": entry.updated_at.isoformat(),
    }


def list_subscriptions() -> PodcastSubscriptionListResponse:
    try:
        with SessionLocal() as session:
            user = get_primary_user(session)
            setting = session.execute(
                select(IntegrationSetting).where(
                    IntegrationSetting.user_id == user.id,
                    IntegrationSetting.integration_key == PODCASTS_INTEGRATION_KEY,
                )
            ).scalar_one_or_none()
            records = _integration_subscriptions(setting.config if setting else {})
            entries = [_subscription_entry(record) for record in records]
            entries.sort(key=lambda entry: entry.updated_at, reverse=True)
            return PodcastSubscriptionListResponse(items=entries)
    except SQLAlchemyError:
        seed_store()
        with STORE.lock:
            entries = [
                _subscription_entry(record)
                for record in STORE.podcast_subscriptions.values()
            ]
        entries.sort(key=lambda entry: entry.updated_at, reverse=True)
        return PodcastSubscriptionListResponse(items=entries)


def create_subscription(payload: PodcastSubscriptionCreateRequest) -> PodcastSubscriptionEntry:
    feed_url = payload.feed_url.strip()
    validate_public_http_url(feed_url)
    now = now_utc()
    entry = PodcastSubscriptionEntry(
        id=_subscription_id(feed_url),
        feed_url=feed_url,
        title=payload.title.strip(),
        author=payload.author.strip() if payload.author else None,
        image_url=payload.image_url.strip() if payload.image_url else None,
        itunes_id=payload.itunes_id.strip() if payload.itunes_id else None,
        page_url=payload.page_url.strip() if payload.page_url else None,
        created_at=now,
        updated_at=now,
    )

    try:
        with SessionLocal() as session:
            user = get_primary_user(session)
            setting = session.execute(
                select(IntegrationSetting).where(
                    IntegrationSetting.user_id == user.id,
                    IntegrationSetting.integration_key == PODCASTS_INTEGRATION_KEY,
                )
            ).scalar_one_or_none()
            if setting is None:
                setting = IntegrationSetting(
                    user_id=user.id,
                    integration_key=PODCASTS_INTEGRATION_KEY,
                    display_name=PODCASTS_DISPLAY_NAME,
                    is_enabled=True,
                    config={"subscriptions": []},
                )
                session.add(setting)
                session.flush()
            records = _integration_subscriptions(setting.config)
            existing = next((record for record in records if record.get("id") == entry.id), None)
            if existing is not None:
                existing.update(_serialize_subscription(entry))
            else:
                records.append(_serialize_subscription(entry))
            setting.config = {"subscriptions": records}
            session.commit()
            return entry
    except SQLAlchemyError:
        seed_store()
        with STORE.lock:
            existing = STORE.podcast_subscriptions.get(entry.id)
            if existing:
                created_at = existing.get("created_at")
                entry.created_at = (
                    created_at if isinstance(created_at, datetime) else entry.created_at
                )
            STORE.podcast_subscriptions[entry.id] = _serialize_subscription(entry)
        return entry


def delete_subscription(subscription_id: str) -> PodcastSubscriptionDeleteResponse:
    try:
        with SessionLocal() as session:
            user = get_primary_user(session)
            setting = session.execute(
                select(IntegrationSetting).where(
                    IntegrationSetting.user_id == user.id,
                    IntegrationSetting.integration_key == PODCASTS_INTEGRATION_KEY,
                )
            ).scalar_one_or_none()
            if setting is None:
                return PodcastSubscriptionDeleteResponse(id=subscription_id, deleted=False)
            records = _integration_subscriptions(setting.config)
            next_records = [
                record for record in records if str(record.get("id")) != subscription_id
            ]
            setting.config = {"subscriptions": next_records}
            session.commit()
            return PodcastSubscriptionDeleteResponse(
                id=subscription_id,
                deleted=len(next_records) != len(records),
            )
    except SQLAlchemyError:
        seed_store()
        with STORE.lock:
            deleted = STORE.podcast_subscriptions.pop(subscription_id, None) is not None
        return PodcastSubscriptionDeleteResponse(id=subscription_id, deleted=deleted)


def _parse_podcast_feed(
    subscription: PodcastSubscriptionEntry,
    limit: int,
) -> list[PodcastEpisodeFeedEntry]:
    xml_text, final_url, _ = _read_feed_xml(subscription.feed_url)
    root = ET.fromstring(xml_text)
    channel = next((child for child in root if _local_name(child.tag) == "channel"), root)
    podcast_title = _normalize_whitespace(_child_text(channel, "title")) or subscription.title
    image_url = subscription.image_url
    image_node = _first_child(channel, "image")
    if image_node is not None:
        image_url = _normalize_whitespace(_child_text(image_node, "url")) or image_url

    items: list[PodcastEpisodeFeedEntry] = []
    for child in channel:
        if _local_name(child.tag) != "item":
            continue
        title = _normalize_whitespace(_child_text(child, "title"))
        enclosure = _first_child(child, "enclosure")
        enclosure_url = _normalize_whitespace(
            enclosure.attrib.get("url") if enclosure is not None else None
        )
        if not title or not enclosure_url:
            continue
        published_at = _parse_datetime(_child_text(child, "pubDate", "published", "updated"))
        guid = _normalize_whitespace(_child_text(child, "guid"))
        episode_id = _episode_identity(final_url, guid, enclosure_url, title, published_at)
        length_value = enclosure.attrib.get("length") if enclosure is not None else None
        try:
            enclosure_length = int(length_value) if length_value else None
        except ValueError:
            enclosure_length = None
        items.append(
            PodcastEpisodeFeedEntry(
                id=episode_id,
                subscription_id=subscription.id,
                feed_url=final_url,
                podcast_title=podcast_title,
                title=title,
                guid=guid,
                link=_normalize_whitespace(_child_text(child, "link")),
                summary=_strip_html(_child_text(child, "description", "encoded", "summary")),
                author=(
                    _normalize_whitespace(_child_text(child, "author", "creator"))
                    or subscription.author
                ),
                published_at=published_at,
                duration_seconds=_parse_duration_seconds(_child_text(child, "duration")),
                enclosure_url=enclosure_url,
                enclosure_type=enclosure.attrib.get("type") if enclosure is not None else None,
                enclosure_length=enclosure_length,
                image_url=image_url,
            )
        )
        if len(items) >= limit:
            break
    return items


def _imported_episode_map() -> dict[str, str]:
    try:
        with SessionLocal() as session:
            user = get_primary_user(session)
            records = session.execute(
                select(ContentItem.id, ContentItem.normalized_url).where(
                    ContentItem.user_id == user.id,
                    ContentItem.content_type == ContentType.podcast_episode.value,
                )
            ).all()
            return {normalized_url: str(item_id) for item_id, normalized_url in records}
    except SQLAlchemyError:
        seed_store()
        with STORE.lock:
            return {
                str(record.get("normalized_url")): str(record["id"])
                for record in STORE.items.values()
                if str(record.get("content_type")) == ContentType.podcast_episode.value
            }


def list_subscription_episodes(limit: int = DEFAULT_EPISODE_LIMIT) -> list[PodcastEpisodeFeedEntry]:
    normalized_limit = max(1, min(limit, MAX_EPISODE_LIMIT))
    subscriptions = list_subscriptions().items
    imported = _imported_episode_map()
    episodes: list[PodcastEpisodeFeedEntry] = []
    per_feed_limit = max(10, normalized_limit)
    for subscription in subscriptions:
        try:
            episodes.extend(_parse_podcast_feed(subscription, per_feed_limit))
        except (ValueError, ET.ParseError):
            continue
    for episode in episodes:
        item_id = imported.get(episode.id)
        if item_id:
            episode.is_imported = True
            episode.item_id = item_id
    episodes.sort(
        key=lambda entry: entry.published_at or datetime.fromtimestamp(0, tz=UTC),
        reverse=True,
    )
    return episodes[:normalized_limit]


def preview_feed_episodes(
    feed_url: str,
    title: str | None = None,
    author: str | None = None,
    image_url: str | None = None,
    limit: int = DEFAULT_EPISODE_LIMIT,
) -> list[PodcastEpisodeFeedEntry]:
    normalized_feed_url = feed_url.strip()
    validate_public_http_url(normalized_feed_url)
    normalized_limit = max(1, min(limit, MAX_EPISODE_LIMIT))
    subscription = PodcastSubscriptionEntry(
        id=_subscription_id(normalized_feed_url),
        feed_url=normalized_feed_url,
        title=(title or "未命名播客").strip() or "未命名播客",
        author=author.strip() if author else None,
        image_url=image_url.strip() if image_url else None,
        itunes_id=None,
        page_url=None,
        created_at=now_utc(),
        updated_at=now_utc(),
    )
    imported = _imported_episode_map()
    try:
        episodes = _parse_podcast_feed(subscription, normalized_limit)
    except ET.ParseError as exc:
        raise ValueError("podcast feed is not valid RSS") from exc
    for episode in episodes:
        episode.subscription_id = None
        item_id = imported.get(episode.id)
        if item_id:
            episode.is_imported = True
            episode.item_id = item_id
    episodes.sort(
        key=lambda entry: entry.published_at or datetime.fromtimestamp(0, tz=UTC),
        reverse=True,
    )
    return episodes[:normalized_limit]


def _fallback_import_episode(payload: PodcastEpisodeImportRequest) -> PodcastEpisodeImportResponse:
    seed_store()
    normalized_url = _episode_identity(
        payload.feed_url,
        payload.guid,
        payload.enclosure_url,
        payload.title,
        payload.published_at,
    )
    with STORE.lock:
        existing = next(
            (
                item
                for item in STORE.items.values()
                if item.get("normalized_url") == normalized_url
            ),
            None,
        )
        if existing is not None:
            return PodcastEpisodeImportResponse(
                uid=str(existing["id"]),
                item_id=str(existing["id"]),
                existing_uid=str(existing["id"]),
                task_id=None,
                status="already_exists",
                content_type=ContentType.podcast_episode,
                folder_id=str(existing.get("folder_id", INBOX_FOLDER_ID)),
                folder_name=str(existing.get("folder_name", INBOX_FOLDER_NAME)),
                is_duplicate=True,
            )
        item_id = str(uuid4())
        task_id = str(uuid4())
        STORE.items[item_id] = {
            "id": item_id,
            "uid": item_id,
            "title": payload.title,
            "content_type": ContentType.podcast_episode.value,
            "source_url": payload.link or payload.enclosure_url,
            "normalized_url": normalized_url,
            "folder_id": INBOX_FOLDER_ID,
            "folder_name": INBOX_FOLDER_NAME,
            "is_inbox": True,
            "status": ItemStatus.pending.value,
            "metadata": {
                "author_name": payload.author,
                "published_at": payload.published_at.isoformat() if payload.published_at else None,
                "site_name": payload.podcast_title,
            },
            "parsed_document": DEFAULT_PARSED_DOCUMENT,
            "transcript": None,
            "summaries": [],
            "highlights": [],
            "notes": [],
            "tags": [],
            "collections": [],
            "reading_state": DEFAULT_READING_STATE.copy(),
            "raw_meta": _podcast_raw_meta(payload),
            "created_at": now_utc(),
            "updated_at": now_utc(),
        }
        STORE.tasks[task_id] = {
            "id": task_id,
            "item_id": item_id,
            "task_type": "fetch_meta",
            "status": TaskStatus.pending.value,
            "attempt_count": 0,
            "error_message": None,
            "created_at": now_utc(),
            "payload": _podcast_task_payload(payload),
        }
    return PodcastEpisodeImportResponse(
        uid=item_id,
        item_id=item_id,
        task_id=task_id,
        status="pending",
        content_type=ContentType.podcast_episode,
        folder_id=INBOX_FOLDER_ID,
        folder_name=INBOX_FOLDER_NAME,
        is_duplicate=False,
    )


def _podcast_raw_meta(payload: PodcastEpisodeImportRequest) -> dict[str, object]:
    return {
        "podcast": {
            "feed_url": payload.feed_url,
            "podcast_title": payload.podcast_title,
            "guid": payload.guid,
            "episode_link": payload.link,
            "enclosure_url": payload.enclosure_url,
            "enclosure_type": payload.enclosure_type,
            "enclosure_length": payload.enclosure_length,
            "image_url": payload.image_url,
            "audio_storage_path": None,
        },
        "metadata": {
            "author_name": payload.author,
            "published_at": payload.published_at.isoformat() if payload.published_at else None,
            "site_name": payload.podcast_title,
        },
        "parsed_document": DEFAULT_PARSED_DOCUMENT,
        "transcript": None,
        "summaries": [],
        "reading_state": DEFAULT_READING_STATE,
        **build_folder_meta(INBOX_FOLDER_ID, INBOX_FOLDER_NAME, True),
    }


def _podcast_task_payload(payload: PodcastEpisodeImportRequest) -> dict[str, object]:
    return {
        "source_url": payload.link or payload.enclosure_url,
        "feed_url": payload.feed_url,
        "podcast_title": payload.podcast_title,
        "title": payload.title,
        "guid": payload.guid,
        "episode_link": payload.link,
        "summary": payload.summary,
        "author": payload.author,
        "published_at": payload.published_at.isoformat() if payload.published_at else None,
        "duration_seconds": payload.duration_seconds,
        "enclosure_url": payload.enclosure_url,
        "enclosure_type": payload.enclosure_type,
        "enclosure_length": payload.enclosure_length,
        "image_url": payload.image_url,
    }


def import_episode(payload: PodcastEpisodeImportRequest) -> PodcastEpisodeImportResponse:
    validate_public_http_url(payload.feed_url)
    validate_public_http_url(payload.enclosure_url)
    normalized_url = _episode_identity(
        payload.feed_url,
        payload.guid,
        payload.enclosure_url,
        payload.title,
        payload.published_at,
    )
    try:
        with SessionLocal() as session:
            user = get_primary_user(session)
            inbox = resolve_folder(session, INBOX_FOLDER_ID)
            if inbox is None:
                raise ValueError("inbox folder not found")
            existing = session.execute(
                select(ContentItem).where(
                    ContentItem.user_id == user.id,
                    ContentItem.normalized_url == normalized_url,
                )
            ).scalar_one_or_none()
            if existing is not None:
                return PodcastEpisodeImportResponse(
                    uid=str(existing.id),
                    item_id=str(existing.id),
                    existing_uid=str(existing.id),
                    task_id=None,
                    status="already_exists",
                    content_type=ContentType.podcast_episode,
                    folder_id=str(existing.folder_id or INBOX_FOLDER_ID),
                    folder_name=inbox.name,
                    is_duplicate=True,
                )
            raw_meta = _podcast_raw_meta(payload)
            item = ContentItem(
                user_id=user.id,
                folder_id=inbox.id,
                content_type=ContentType.podcast_episode.value,
                source_platform="podcast",
                source_url=payload.link or payload.enclosure_url,
                normalized_url=normalized_url,
                external_id=payload.guid,
                title=payload.title,
                subtitle=payload.podcast_title,
                author_name=payload.author,
                author_id=None,
                cover_url=payload.image_url,
                duration_seconds=payload.duration_seconds,
                language=None,
                published_at=payload.published_at,
                status=ItemStatus.pending.value,
                visibility="private",
                raw_meta=raw_meta,
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
                payload=_podcast_task_payload(payload),
                result={},
                error_message=None,
                started_at=None,
                finished_at=None,
                next_retry_at=None,
            )
            session.add(task)
            session.commit()
            return PodcastEpisodeImportResponse(
                uid=str(item.id),
                item_id=str(item.id),
                task_id=str(task.id),
                status="pending",
                content_type=ContentType.podcast_episode,
                folder_id=str(inbox.id),
                folder_name=inbox.name,
                is_duplicate=False,
            )
    except SQLAlchemyError:
        return _fallback_import_episode(payload)
