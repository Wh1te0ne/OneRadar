from __future__ import annotations

import asyncio
import logging
import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db.models import User
from app.db.session import SessionLocal
from app.schemas.feeds import FeedRefreshResponse
from app.services.db_access import get_primary_user
from app.services.feed_service import preview_feed
from app.services.feed_state_service import (
    get_feed_state,
    mark_feed_source_error,
    upsert_feed_cache,
)
from app.services.settings_service import (
    FeedRefreshRuntimeSettings,
    get_feed_refresh_runtime_settings,
)
from app.services.user_context import reset_current_user_id, set_current_user_id

logger = logging.getLogger(__name__)
MAX_SETTINGS_POLL_SECONDS = 30


def _refresh_current_user_feeds(limit: int) -> FeedRefreshResponse:
    state = get_feed_state()
    errors: dict[str, str] = {}
    refreshed = 0

    for source in state.sources:
        try:
            feed = preview_feed(source.source_url, limit=limit)
            upsert_feed_cache(feed)
            refreshed += 1
        except Exception as error:  # RSS refresh should keep the rest of the sources moving.
            message = str(error)
            errors[source.source_url] = message
            mark_feed_source_error(source.source_url, source.site_title, message)

    return FeedRefreshResponse(
        total=len(state.sources),
        refreshed=refreshed,
        failed=len(errors),
        errors=errors,
    )


def _all_user_ids() -> list[object]:
    with SessionLocal() as session:
        get_primary_user(session)
        user_ids = list(session.execute(select(User.id).order_by(User.created_at.asc())).scalars())
        session.commit()
        return user_ids


def refresh_all_feeds(limit: int = 0) -> FeedRefreshResponse:
    total = 0
    refreshed = 0
    failed = 0
    errors: dict[str, str] = {}

    for user_id in _all_user_ids():
        token = set_current_user_id(user_id)
        try:
            result = _refresh_current_user_feeds(limit)
        finally:
            reset_current_user_id(token)
        total += result.total
        refreshed += result.refreshed
        failed += result.failed
        errors.update(result.errors)

    return FeedRefreshResponse(total=total, refreshed=refreshed, failed=failed, errors=errors)


def seconds_until_next_refresh(
    now: datetime,
    settings: FeedRefreshRuntimeSettings,
) -> int:
    current = now.astimezone(UTC)
    if settings.interval_unit == "hours":
        interval_hours = max(1, min(24, settings.interval_value))
        current_hour = current.replace(minute=0, second=0, microsecond=0)
        for offset in range(0, 25):
            candidate = current_hour + timedelta(hours=offset)
            if candidate <= current:
                continue
            if candidate.hour % interval_hours == 0:
                return max(1, math.ceil((candidate - current).total_seconds()))
        return interval_hours * 3600

    interval_minutes = max(1, min(60, settings.interval_value))
    current_hour = current.replace(minute=0, second=0, microsecond=0)
    for minute in range(0, 60, interval_minutes):
        candidate = current_hour + timedelta(minutes=minute)
        if candidate > current:
            return max(1, math.ceil((candidate - current).total_seconds()))
    next_hour = current_hour + timedelta(hours=1)
    return max(1, math.ceil((next_hour - current).total_seconds()))


async def _sleep_until_next_refresh() -> None:
    while True:
        settings = get_feed_refresh_runtime_settings()
        if not settings.enabled:
            await asyncio.sleep(MAX_SETTINGS_POLL_SECONDS)
            continue
        seconds = seconds_until_next_refresh(datetime.now(UTC), settings)
        await asyncio.sleep(min(seconds, MAX_SETTINGS_POLL_SECONDS))
        if seconds <= MAX_SETTINGS_POLL_SECONDS:
            return


async def run_feed_refresh_loop(interval_seconds: int, startup_delay_seconds: int) -> None:
    _ = interval_seconds
    startup_delay = max(0, startup_delay_seconds)
    if startup_delay:
        await asyncio.sleep(startup_delay)

    while True:
        await _sleep_until_next_refresh()
        try:
            result = await asyncio.to_thread(refresh_all_feeds)
            if result.total:
                logger.info(
                    "RSS auto refresh finished: total=%s refreshed=%s failed=%s",
                    result.total,
                    result.refreshed,
                    result.failed,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("RSS auto refresh failed")
