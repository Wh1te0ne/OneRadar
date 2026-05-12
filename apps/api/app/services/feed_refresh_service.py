from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.db.models import User
from app.db.session import SessionLocal
from app.schemas.feeds import FeedRefreshResponse
from app.services.db_access import get_primary_user
from app.services.feed_service import preview_feed
from app.services.feed_state_service import get_feed_state, mark_feed_source_error, upsert_feed_cache
from app.services.user_context import reset_current_user_id, set_current_user_id

logger = logging.getLogger(__name__)


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


async def run_feed_refresh_loop(interval_seconds: int, startup_delay_seconds: int) -> None:
    interval = max(60, interval_seconds)
    startup_delay = max(0, startup_delay_seconds)
    if startup_delay:
        await asyncio.sleep(startup_delay)

    while True:
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
        await asyncio.sleep(interval)
