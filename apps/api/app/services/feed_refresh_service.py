from __future__ import annotations

import asyncio
import logging

from app.schemas.feeds import FeedRefreshResponse
from app.services.feed_service import preview_feed
from app.services.feed_state_service import get_feed_state, mark_feed_source_error, upsert_feed_cache

logger = logging.getLogger(__name__)


def refresh_all_feeds(limit: int = 0) -> FeedRefreshResponse:
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
