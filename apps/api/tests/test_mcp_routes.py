from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from app.schemas.feeds import FeedRefreshResponse
from app.services import feed_state_service
from app.services.feed_translation_service import FeedTranslationResult


def _use_file_feed_state(monkeypatch) -> Path:
    def failing_session_local():
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(feed_state_service, "SessionLocal", failing_session_local)
    state_path = Path(".tmp") / f"mcp-feed-state-{uuid4().hex}.json"
    monkeypatch.setenv("ONERADAR_FEED_STATE_PATH", str(state_path))
    return state_path


def test_mcp_lists_hermes_news_tools(client) -> None:
    response = client.post(
        "/api/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 1
    tool_names = {tool["name"] for tool in body["result"]["tools"]}
    assert {
        "get_news_window",
        "get_news_window_status",
        "get_news_sources",
        "refresh_news",
    } <= tool_names


def test_mcp_refresh_news_waits_for_refresh_and_returns_entries(client, monkeypatch) -> None:
    from app.services import mcp_news_service

    feed_payload = {
        "source_url": "https://example.com/rss.xml",
        "site_title": "Example Feed",
        "site_url": "https://example.com/",
        "description": "Example description",
        "items": [
            {
                "id": "fresh-after-refresh",
                "title": "刷新后的新闻",
                "link": "https://example.com/fresh-after-refresh",
                "summary": "刷新以后出现的中文摘要。",
                "author": "Ada",
                "published_at": "2026-06-25T00:30:00Z",
                "tags": ["AI"],
            }
        ],
        "fetched_at": "2026-06-25T00:31:00Z",
    }
    assert client.post("/api/feeds/cache", json={"feed": feed_payload}).status_code == 200
    cached_state = client.get("/api/feeds/state", params={"window": "all"}).json()
    assert cached_state["feeds"]["https://example.com/rss.xml"]["items"][0]["id"] == (
        "fresh-after-refresh"
    )
    assert cached_state["feeds"]["https://example.com/rss.xml"]["items"][0]["published_at"].startswith(
        "2026-06-25T00:30:00"
    )

    refresh_calls = []

    def fake_refresh_current_user_feeds(limit: int = 0):
        refresh_calls.append(limit)
        return SimpleNamespace(
            refresh=FeedRefreshResponse(total=1, refreshed=1, failed=0, errors={}),
            translation=FeedTranslationResult(total=1, translated=1, skipped=0, failed=0),
        )

    monkeypatch.setattr(
        mcp_news_service,
        "refresh_current_user_feeds",
        fake_refresh_current_user_feeds,
        raising=False,
    )

    response = client.post(
        "/api/mcp",
        json={
            "jsonrpc": "2.0",
            "id": "refresh",
            "method": "tools/call",
            "params": {
                "name": "refresh_news",
                "arguments": {
                    "since": "2026-06-25T00:00:00Z",
                    "until": "2026-06-25T08:30:00Z",
                    "include_entries": True,
                    "limit": 20,
                },
            },
        },
    )

    assert response.status_code == 200, response.json()
    result = response.json()["result"]
    assert result["isError"] is False
    payload = result["structuredContent"]
    assert refresh_calls == [0]
    assert payload["ready"] is True
    assert payload["status"] == "completed"
    assert payload["refresh"] == {"total": 1, "refreshed": 1, "failed": 0, "errors": {}}
    assert payload["translation"] == {
        "total": 1,
        "translated": 1,
        "skipped": 0,
        "failed": 0,
        "status": "completed",
    }
    assert payload["total"] == 1, payload
    assert payload["entries"][0]["id"] == "fresh-after-refresh"
    assert payload["entries"][0]["summary"] == "刷新以后出现的中文摘要。"


def test_mcp_get_news_window_returns_raw_entries_for_requested_window(client, monkeypatch) -> None:
    state_path = _use_file_feed_state(monkeypatch)
    try:
        feed_payload = {
            "source_url": "https://example.com/rss.xml",
            "site_title": "Example Feed",
            "site_url": "https://example.com/",
            "description": "Example description",
            "items": [
                {
                    "id": "fresh-1",
                    "title": "Fresh Entry",
                    "link": "https://example.com/fresh-1",
                    "summary": "Fresh summary",
                    "author": "Ada",
                    "published_at": "2026-05-09T00:30:00Z",
                    "tags": ["AI"],
                },
                {
                    "id": "old-1",
                    "title": "Old Entry",
                    "link": "https://example.com/old-1",
                    "summary": "Old summary",
                    "author": "Ada",
                    "published_at": "2026-05-07T23:59:00Z",
                    "tags": [],
                },
            ],
            "fetched_at": "2026-05-09T01:00:00Z",
        }
        assert client.post("/api/feeds/cache", json={"feed": feed_payload}).status_code == 200

        response = client.post(
            "/api/mcp",
            json={
                "jsonrpc": "2.0",
                "id": "window",
                "method": "tools/call",
                "params": {
                    "name": "get_news_window",
                    "arguments": {
                        "since": "2026-05-08T00:00:00Z",
                        "until": "2026-05-09T08:30:00Z",
                    },
                },
            },
        )

        assert response.status_code == 200, response.json()
        result = response.json()["result"]
        assert result["isError"] is False
        assert result["content"][0]["type"] == "text"
        payload = result["structuredContent"]
        assert payload["window"] == {
            "since": "2026-05-08T00:00:00+00:00",
            "until": "2026-05-09T08:30:00+00:00",
        }
        assert payload["total"] == 1
        assert payload["sources"][0]["source_url"] == "https://example.com/rss.xml"
        assert payload["sources"][0]["entry_count"] == 1
        assert payload["entries"][0]["id"] == "fresh-1"
        assert payload["entries"][0]["title"] == "Fresh Entry"
        assert payload["entries"][0]["summary"] == "Fresh summary"
        assert payload["entries"][0]["source_title"] == "Example Feed"
        assert payload["entries"][0]["published_at"] == "2026-05-09T00:30:00+00:00"
        assert payload["entries"][0]["url"] == "https://example.com/fresh-1"
    finally:
        state_path.unlink(missing_ok=True)
