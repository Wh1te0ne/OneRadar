from __future__ import annotations

from datetime import UTC, datetime

from app.services.feed_refresh_service import seconds_until_next_refresh
from app.services.settings_service import FeedRefreshRuntimeSettings


def test_minute_refresh_interval_is_aligned_to_hour_boundary() -> None:
    settings = FeedRefreshRuntimeSettings(enabled=True, interval_value=30, interval_unit="minutes")
    now = datetime(2026, 6, 25, 2, 7, 15, tzinfo=UTC)

    assert seconds_until_next_refresh(now, settings) == 22 * 60 + 45


def test_hour_refresh_interval_is_aligned_to_clock_hour() -> None:
    settings = FeedRefreshRuntimeSettings(enabled=True, interval_value=2, interval_unit="hours")
    now = datetime(2026, 6, 25, 3, 20, 0, tzinfo=UTC)

    assert seconds_until_next_refresh(now, settings) == 40 * 60


def test_feed_refresh_settings_api_round_trips(client) -> None:
    response = client.put(
        "/api/settings/feed-refresh",
        json={"enabled": True, "interval_value": 45, "interval_unit": "minutes"},
    )

    assert response.status_code == 200, response.json()
    assert response.json()["interval_seconds"] == 2700

    loaded = client.get("/api/settings/feed-refresh")
    assert loaded.status_code == 200
    assert loaded.json()["interval_value"] == 45
    assert loaded.json()["interval_unit"] == "minutes"
