from __future__ import annotations

import json
from datetime import UTC, datetime
from os import getenv
from pathlib import Path
from threading import Lock

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from app.db.models import FeedEntry, FeedEntryReadState, FeedSource
from app.db.session import SessionLocal
from app.schemas.feeds import (
    FeedPreviewItem,
    FeedPreviewResponse,
    FeedSourceEntry,
    FeedStateResponse,
)
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


def _file_feed_state() -> FeedStateResponse:
    with _STATE_LOCK:
        state = _load_file_state()
    sources: list[FeedSourceEntry] = []
    for source in state["sources"]:
        if not isinstance(source, dict):
            continue
        try:
            sources.append(FeedSourceEntry.model_validate(source))
        except ValueError:
            continue

    feeds: dict[str, FeedPreviewResponse] = {}
    for key, feed in dict(state["feeds"]).items():
        if not isinstance(key, str) or not isinstance(feed, dict):
            continue
        try:
            feeds[key] = FeedPreviewResponse.model_validate(feed)
        except ValueError:
            continue

    read_entries = [
        entry
        for entry in state["read_entries"]
        if isinstance(entry, str) and entry.strip()
    ]
    return FeedStateResponse(sources=sources, feeds=feeds, read_entries=read_entries)


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


def _source_entry(record: FeedSource) -> FeedSourceEntry:
    return FeedSourceEntry(
        source_url=record.source_url,
        site_title=record.site_title,
        site_url=record.site_url,
        description=record.description,
        last_loaded_at=record.last_loaded_at,
        last_refresh_status=record.last_refresh_status,
        last_refresh_error=record.last_refresh_error,
        last_refreshed_at=record.last_refreshed_at,
    )


def _feed_response(record: FeedSource, read_entry_ids: set[str]) -> FeedPreviewResponse:
    items = [
        _with_saved_state(
            FeedPreviewItem(
                id=entry.entry_id,
                title=entry.title,
                link=entry.link,
                summary=entry.summary,
                author=entry.author,
                published_at=entry.published_at,
                tags=list(entry.tags or []),
            )
        )
        for entry in sorted(
            record.entries,
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


def get_feed_state() -> FeedStateResponse:
    try:
        with SessionLocal() as session:
            user = get_primary_user(session)
            sources = session.execute(
                select(FeedSource)
                .where(FeedSource.user_id == user.id)
                .options(selectinload(FeedSource.entries))
                .order_by(FeedSource.last_loaded_at.desc())
            ).scalars().all()
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
                sources=[_source_entry(source) for source in sources],
                feeds={source.source_url: _feed_response(source, read_ids) for source in sources},
                read_entries=read_entries,
            )
    except SQLAlchemyError:
        return _file_feed_state()


def upsert_feed_cache(feed: FeedPreviewResponse) -> FeedStateResponse:
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
                entry.title = item.title
                entry.link = item.link
                entry.summary = item.summary
                entry.author = item.author
                entry.published_at = item.published_at
                entry.tags = list(item.tags or [])
                entry.raw_item = item.model_dump(mode="json")
            session.commit()
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
