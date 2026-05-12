from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

from app.db.models import User
from app.db.session import SessionLocal
from app.services.db_access import get_primary_user
from app.services.daily_news_service import generate_today_if_missing
from app.services.user_context import reset_current_user_id, set_current_user_id

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
            reports = await asyncio.to_thread(_generate_for_all_users)
            for report in reports:
                logger.info("Daily news report generated for %s", report.report_date)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Daily news report generation failed")


def _generate_for_all_users() -> list[object]:
    with SessionLocal() as session:
        get_primary_user(session)
        user_ids = list(session.execute(select(User.id).order_by(User.created_at.asc())).scalars())
        session.commit()

    reports: list[object] = []
    for user_id in user_ids:
        token = set_current_user_id(user_id)
        try:
            report = generate_today_if_missing()
            if report is not None:
                reports.append(report)
        finally:
            reset_current_user_id(token)
    return reports
