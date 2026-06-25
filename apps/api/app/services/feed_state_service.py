from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from os import getenv
from pathlib import Path
from threading import Lock

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import FeedEntry, FeedEntryReadState, FeedSource
from app.db.session import SessionLocal
from app.schemas.feeds import (
    FeedPreviewItem,
    FeedPreviewResponse,
    FeedSourceEntry,
    FeedStateResponse,
)
from app.services import feed_translation_service
from app.services.db_access import get_primary_user
from app.services.items_service import find_saved_item_for_url

_STATE_LOCK = Lock()
_DEFAULT_STATE = {"sources": [], "feeds": {}, "read_entries": []}


def _state_path() -> Path:
    configured = getenv("ONERADAR_FEED_STATE_PATH")
    if configured:
        return Path(configured)
    return Path.cwd() / "oneradar_feed_state.json"


def _load_file_state() -> dict[str, object]:
    path = _state_path()
    if not path.exists():
        return dict(_DEFAULT_STATE)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(_DEFAULT_STATE)
    if not isinstance(data, dict):
        return dict(_DEFAULT_STATE)
    return {
        "sources": data.get("sources") if isinstance(data.get("sources"), list) else [],
        "feeds": data.get("feeds") if isinstance(data.get("feeds"), dict) else {},
        "read_entries": (
            data.get("read_entries")
            if isinstance(data.get("read_entries"), list)
            else []
        ),
    }


def _save_file_state(state: dict[str, object]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _window_bounds(window: str = "all", since: datetime | None = None, until: datetime | None = None) -> tuple[str, datetime | None, datetime | None]:
    normalized = (window or "all").strip().lower()
    now = datetime.now(UTC)
    if since is not None or until is not None:
        return "custom", since, until or now
    if normalized == "today":
        local_now = now.astimezone()
        start = local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
        return "today", start, now
    if normalized in {"week", "7d", "recent"}:
        return "week", now - timedelta(days=7), now
    return "all", None, None


def _in_window(value: datetime | None, start: datetime | None, end: datetime | None) -> bool:
    if value is None:
        return start is None and end is None
    current = value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if start is not None and current < start:
        return False
    if end is not None and current > end:
        return False
    return True


def _count_windows(values: list[datetime | None]) -> tuple[int, int, int]:
    _, today_start, today_end = _window_bounds("today")
    _, week_start, week_end = _window_bounds("week")
    return (
        len(values),
        sum(1 for value in values if _in_window(value, today_start, today_end)),
        sum(1 for value in values if _in_window(value, week_start, week_end)),
    )


def _file_feed_state(window: str = "all", since: datetime | None = None, until: datetime | None = None) -> FeedStateResponse:
    normalized_window, start, end = _window_bounds(window, since, until)
    with _STATE_LOCK:
        state = _load_file_state()
    sources: list[FeedSourceEntry] = []
    raw_feeds = dict(state["feeds"])
    for source in state["sources"]:
        if not isinstance(source, dict):
            continue
        source_url = str(source.get("source_url") or "")
        raw_items = []
        raw_feed = raw_feeds.get(source_url)
        if isinstance(raw_feed, dict) and isinstance(raw_feed.get("items"), list):
            raw_items = [item for item in raw_feed["items"] if isinstance(item, dict)]
        published_values = []
        for item in raw_items:
            try:
                value = item.get("published_at")
                published_values.append(datetime.fromisoformat(str(value)) if value else None)
            except ValueError:
                published_values.append(None)
        entry_count, today_count, week_count = _count_windows(published_values)
        enriched = {
            **source,
            "entry_count": entry_count,
            "today_count": today_count,
            "week_count": week_count,
        }
        try:
            sources.append(FeedSourceEntry.model_validate(enriched))
        except ValueError:
            continue

    feeds: dict[str, FeedPreviewResponse] = {}
    for key, feed in raw_feeds.items():
        if not isinstance(key, str) or not isinstance(feed, dict):
            continue
        next_feed = dict(feed)
        raw_items = next_feed.get("items")
        if isinstance(raw_items, list) and normalized_window != "all":
            filtered_items = []
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                published_at = item.get("published_at")
                try:
                    parsed_at = datetime.fromisoformat(str(published_at)) if published_at else None
                except ValueError:
                    parsed_at = None
                if _in_window(parsed_at, start, end):
                    filtered_items.append(item)
            next_feed["items"] = filtered_items
        try:
            feeds[key] = FeedPreviewResponse.model_validate(next_feed)
        except ValueError:
            continue

    read_entries = [
        entry
        for entry in state["read_entries"]
        if isinstance(entry, str) and entry.strip()
    ]
    return FeedStateResponse(sources=sources, feeds=feeds, read_entries=read_entries, window=normalized_window)


def _entry_read_key(source_url: str, entry_id: str) -> str:
    return f"{source_url}:{entry_id}"


def _entry_read_keys(source_url: str, entry: FeedEntry) -> set[str]:
    return {
        key
        for key in (
            _entry_read_key(source_url, entry.entry_id),
            _entry_read_key(source_url, entry.link),
        )
        if key.strip()
    }


def _with_saved_state(item: FeedPreviewItem) -> FeedPreviewItem:
    saved = find_saved_item_for_url(item.link)
    if saved is None:
        return item
    item.is_saved = True
    item.saved_item_id = saved["item_id"]
    item.saved_uid = saved["uid"]
    return item


def _source_entry(record: FeedSource, counts: tuple[int, int, int] = (0, 0, 0)) -> FeedSourceEntry:
    entry_count, today_count, week_count = counts
    return FeedSourceEntry(
        source_url=record.source_url,
        site_title=record.site_title,
        site_url=record.site_url,
        description=record.description,
        last_loaded_at=record.last_loaded_at,
        last_refresh_status=record.last_refresh_status,
        last_refresh_error=record.last_refresh_error,
        last_refreshed_at=record.last_refreshed_at,
        entry_count=entry_count,
        today_count=today_count,
        week_count=week_count,
    )


def _feed_response(record: FeedSource, entries: list[FeedEntry], read_entry_ids: set[str]) -> FeedPreviewResponse:
    items = [
        _with_saved_state(
            FeedPreviewItem(
                id=entry.entry_id,
                title=entry.title,
                translated_title=entry.translated_title,
                display_title=feed_translation_service.display_feed_title(
                    entry.title,
                    entry.translated_title,
                ),
                link=entry.link,
                summary=entry.summary,
                translated_summary=entry.translated_summary,
                display_summary=feed_translation_service.display_feed_summary(
                    entry.summary,
                    entry.translated_summary,
                ),
                translation_status=entry.translation_status,
                translation_provider=entry.translation_provider,
                translation_model=entry.translation_model,
                translated_at=entry.translated_at,
                author=entry.author,
                published_at=entry.published_at,
                tags=list(entry.tags or []),
            )
        )
        for entry in sorted(
            entries,
            key=lambda item: item.published_at or datetime.fromtimestamp(0, tz=UTC),
            reverse=True,
        )
    ]
    _ = read_entry_ids
    return FeedPreviewResponse(
        source_url=record.source_url,
        site_title=record.site_title,
        site_url=record.site_url,
        description=record.description,
        items=items,
        fetched_at=record.last_loaded_at,
    )


def get_feed_state(window: str = "all", since: datetime | None = None, until: datetime | None = None) -> FeedStateResponse:
    normalized_window, start, end = _window_bounds(window, since, until)
    try:
        with SessionLocal() as session:
            user = get_primary_user(session)
            sources = session.execute(
                select(FeedSource)
                .where(FeedSource.user_id == user.id)
                .order_by(FeedSource.last_loaded_at.desc())
            ).scalars().all()
            source_ids = [source.id for source in sources]
            count_rows = []
            entries_by_source: dict[object, list[FeedEntry]] = {source.id: [] for source in sources}
            if source_ids:
                count_rows = session.execute(
                    select(FeedEntry.feed_source_id, FeedEntry.published_at)
                    .where(FeedEntry.feed_source_id.in_(source_ids))
                ).all()
                entries_query = select(FeedEntry).where(FeedEntry.feed_source_id.in_(source_ids))
                if start is not None:
                    entries_query = entries_query.where(FeedEntry.published_at >= start)
                if end is not None:
                    entries_query = entries_query.where(FeedEntry.published_at <= end)
                entries = session.execute(entries_query).scalars().all()
                for entry in entries:
                    entries_by_source.setdefault(entry.feed_source_id, []).append(entry)
            counts_by_source: dict[object, tuple[int, int, int]] = {}
            for source in sources:
                published_values = [
                    published_at
                    for feed_source_id, published_at in count_rows
                    if feed_source_id == source.id
                ]
                counts_by_source[source.id] = _count_windows(published_values)
            read_states = session.execute(
                select(FeedEntryReadState, FeedEntry, FeedSource)
                .join(FeedEntry, FeedEntryReadState.feed_entry_id == FeedEntry.id)
                .join(FeedSource, FeedEntry.feed_source_id == FeedSource.id)
                .where(FeedEntryReadState.user_id == user.id)
            ).all()
            read_entries = [
                _entry_read_key(source.source_url, entry.entry_id)
                for _, entry, source in read_states
            ]
            read_ids = {str(entry.id) for _, entry, _ in read_states}
            return FeedStateResponse(
                sources=[_source_entry(source, counts_by_source.get(source.id, (0, 0, 0))) for source in sources],
                feeds={
                    source.source_url: _feed_response(
                        source,
                        entries_by_source.get(source.id, []),
                        read_ids,
                    )
                    for source in sources
                },
                read_entries=read_entries,
                window=normalized_window,
            )
    except SQLAlchemyError:
        return _file_feed_state(normalized_window, start, end)


def upsert_feed_cache(feed: FeedPreviewResponse) -> FeedStateResponse:
    translation_entry_ids = []
    try:
        with SessionLocal() as session:
            user = get_primary_user(session)
            source = session.execute(
                select(FeedSource).where(
                    FeedSource.user_id == user.id,
                    FeedSource.source_url == feed.source_url,
                )
            ).scalar_one_or_none()
            if source is None:
                source = FeedSource(
                    user_id=user.id,
                    source_url=feed.source_url,
                    site_title=feed.site_title,
                    site_url=feed.site_url,
                    description=feed.description,
                    last_loaded_at=feed.fetched_at,
                )
                session.add(source)
                session.flush()
            else:
                source.site_title = feed.site_title
                source.site_url = feed.site_url
                source.description = feed.description
                source.last_loaded_at = feed.fetched_at
            source.last_refresh_status = "success"
            source.last_refresh_error = None
            source.last_refreshed_at = datetime.now(UTC)

            existing_entries = {
                entry.entry_id: entry
                for entry in session.execute(
                    select(FeedEntry).where(FeedEntry.feed_source_id == source.id)
                ).scalars()
            }
            for item in feed.items:
                entry = existing_entries.get(item.id)
                if entry is None:
                    entry = FeedEntry(
                        user_id=user.id,
                        feed_source_id=source.id,
                        entry_id=item.id,
                        title=item.title,
                        link=item.link,
                    )
                    session.add(entry)
                    session.flush()
                    translation_entry_ids.append(entry.id)
                entry.title = item.title
                entry.link = item.link
                entry.summary = item.summary
                source_hash = feed_translation_service.feed_translation_source_hash(
                    entry.title,
                    entry.summary,
                )
                if entry.translation_source_hash != source_hash:
                    entry.translated_title = None
                    entry.translated_summary = None
                    entry.translation_language = None
                    entry.translation_provider = None
                    entry.translation_model = None
                    entry.translation_status = "pending"
                    entry.translation_error = None
                    entry.translation_source_hash = source_hash
                    entry.translated_at = None
                    if entry.id not in translation_entry_ids:
                        translation_entry_ids.append(entry.id)
                entry.author = item.author
                entry.published_at = item.published_at
                entry.tags = list(item.tags or [])
                entry.raw_item = item.model_dump(mode="json")
            session.commit()
        feed_translation_service.translate_feed_entries(entry_ids=translation_entry_ids)
        return get_feed_state()
    except SQLAlchemyError:
        with _STATE_LOCK:
            state = _load_file_state()
            feeds = dict(state["feeds"])
            previous_feed = feeds.get(feed.source_url)
            previous_items = []
            if isinstance(previous_feed, dict) and isinstance(previous_feed.get("items"), list):
                previous_items = [
                    item
                    for item in previous_feed["items"]
                    if isinstance(item, dict)
                ]
            merged_items = {
                str(item.get("id") or item.get("link") or ""): item
                for item in previous_items
                if str(item.get("id") or item.get("link") or "").strip()
            }
            for item in feed.model_dump(mode="json")["items"]:
                key = str(item.get("id") or item.get("link") or "")
                if key.strip():
                    merged_items[key] = item
            next_feed = feed.model_dump(mode="json")
            next_feed["items"] = list(merged_items.values())
            feeds[feed.source_url] = next_feed
            sources = [
                source
                for source in list(state["sources"])
                if isinstance(source, dict) and source.get("source_url") != feed.source_url
            ]
            sources.insert(
                0,
                {
                    "source_url": feed.source_url,
                    "site_title": feed.site_title,
                    "site_url": feed.site_url,
                    "description": feed.description,
                    "last_loaded_at": feed.fetched_at.isoformat(),
                    "last_refresh_status": "success",
                    "last_refresh_error": None,
                    "last_refreshed_at": datetime.now(UTC).isoformat(),
                },
            )
            state["feeds"] = feeds
            state["sources"] = sources[:30]
            _save_file_state(state)
        return _file_feed_state()


def mark_feed_source_error(
    source_url: str,
    site_title: str | None,
    error_message: str,
) -> FeedStateResponse:
    normalized = source_url.strip()
    if not normalized:
        return get_feed_state()
    try:
        with SessionLocal() as session:
            user = get_primary_user(session)
            source = session.execute(
                select(FeedSource).where(
                    FeedSource.user_id == user.id,
                    FeedSource.source_url == normalized,
                )
            ).scalar_one_or_none()
            if source is None:
                source = FeedSource(
                    user_id=user.id,
                    source_url=normalized,
                    site_title=site_title or normalized,
                    site_url=None,
                    description=None,
                    last_loaded_at=datetime.now(UTC),
                )
                session.add(source)
            source.last_refresh_status = "failed"
            source.last_refresh_error = error_message.strip()
            source.last_refreshed_at = datetime.now(UTC)
            session.commit()
        return get_feed_state()
    except SQLAlchemyError:
        with _STATE_LOCK:
            state = _load_file_state()
            sources = [
                source
                for source in list(state["sources"])
                if isinstance(source, dict) and source.get("source_url") != normalized
            ]
            sources.insert(
                0,
                {
                    "source_url": normalized,
                    "site_title": site_title or normalized,
                    "description": None,
                    "last_loaded_at": datetime.now(UTC).isoformat(),
                    "last_refresh_status": "failed",
                    "last_refresh_error": error_message.strip(),
                    "last_refreshed_at": datetime.now(UTC).isoformat(),
                },
            )
            state["sources"] = sources[:30]
            _save_file_state(state)
        return _file_feed_state()


def mark_feed_entry_read(entry_key: str) -> FeedStateResponse:
    normalized = entry_key.strip()
    try:
        with SessionLocal() as session:
            user = get_primary_user(session)
            rows = session.execute(
                select(FeedEntry, FeedSource)
                .join(FeedSource, FeedEntry.feed_source_id == FeedSource.id)
                .where(FeedEntry.user_id == user.id)
            ).all()
            target_entry = next(
                (
                    entry
                    for entry, source in rows
                    if normalized in _entry_read_keys(source.source_url, entry)
                ),
                None,
            )
            if target_entry is not None:
                existing = session.execute(
                    select(FeedEntryReadState).where(
                        FeedEntryReadState.user_id == user.id,
                        FeedEntryReadState.feed_entry_id == target_entry.id,
                    )
                ).scalar_one_or_none()
                if existing is None:
                    session.add(
                        FeedEntryReadState(
                            user_id=user.id,
                            feed_entry_id=target_entry.id,
                            read_at=datetime.now(UTC),
                        )
                    )
                    session.commit()
        return get_feed_state()
    except SQLAlchemyError:
        with _STATE_LOCK:
            state = _load_file_state()
            read_entries = [
                entry
                for entry in list(state["read_entries"])
                if isinstance(entry, str) and entry.strip()
            ]
            if normalized and normalized not in read_entries:
                read_entries.append(normalized)
            state["read_entries"] = read_entries
            _save_file_state(state)
        return _file_feed_state()


def delete_feed_source(source_url: str) -> bool:
    normalized = source_url.strip()
    try:
        with SessionLocal() as session:
            user = get_primary_user(session)
            result = session.execute(
                delete(FeedSource).where(
                    FeedSource.user_id == user.id,
                    FeedSource.source_url == normalized,
                )
            )
            session.commit()
            return bool(result.rowcount)
    except SQLAlchemyError:
        with _STATE_LOCK:
            state = _load_file_state()
            feeds = dict(state["feeds"])
            deleted = normalized in feeds
            feeds.pop(normalized, None)
            sources = [
                source
                for source in list(state["sources"])
                if isinstance(source, dict) and source.get("source_url") != normalized
            ]
            deleted = deleted or len(sources) != len(state["sources"])
            state["feeds"] = feeds
            state["sources"] = sources
            _save_file_state(state)
        return deleted
