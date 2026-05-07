from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.services.daily_news_service import generate_today_if_missing

logger = logging.getLogger(__name__)


async def run_daily_news_generation_loop(hour: int, timezone_name: str) -> None:
    normalized_hour = max(0, min(23, hour))
    try:
        tz = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("Asia/Shanghai")

    while True:
        now = datetime.now(tz)
        next_run = now.replace(hour=normalized_hour, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        await asyncio.sleep(max(1, (next_run - now).total_seconds()))
        try:
            report = await asyncio.to_thread(generate_today_if_missing)
            if report is not None:
                logger.info("Daily news report generated for %s", report.report_date)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Daily news report generation failed")
