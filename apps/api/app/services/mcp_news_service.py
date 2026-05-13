from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException

from app.schemas.feeds import FeedPreviewItem, FeedPreviewResponse, FeedSourceEntry
from app.services.feed_state_service import get_feed_state

MCP_PROTOCOL_VERSION = "2025-06-18"
MAX_WINDOW_LIMIT = 2000
DEFAULT_WINDOW_LIMIT = 1000


def handle_mcp_request(payload: dict[str, Any]) -> dict[str, Any]:
    request_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}

    try:
        if method == "initialize":
            result = {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "serverInfo": {"name": "oneradar-news", "version": "1.0.0"},
                "capabilities": {"tools": {}},
            }
        elif method == "tools/list":
            result = {"tools": _tools()}
        elif method == "tools/call":
            result = _call_tool(params)
        else:
            return _json_rpc_error(request_id, -32601, f"Unsupported MCP method: {method}")
    except HTTPException as exc:
        return _json_rpc_error(request_id, -32602, str(exc.detail))
    except ValueError as exc:
        return _json_rpc_error(request_id, -32602, str(exc))

    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _call_tool(params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
    if name == "get_news_sources":
        payload = get_news_sources()
    elif name == "get_news_window_status":
        payload = get_news_window_status(**arguments)
    elif name == "get_news_window":
        payload = get_news_window(**arguments)
    else:
        raise ValueError(f"Unknown tool: {name}")
    return _tool_result(payload)


def get_news_sources() -> dict[str, Any]:
    state = get_feed_state()
    sources = [
        _source_payload(source, state.feeds.get(source.source_url))
        for source in state.sources
    ]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "total": len(sources),
        "sources": sources,
    }


def get_news_window_status(
    since: str | None = None,
    until: str | None = None,
    source_urls: list[str] | None = None,
) -> dict[str, Any]:
    return _news_window_payload(
        since=since,
        until=until,
        source_urls=source_urls,
        limit=0,
        cursor=None,
        include_entries=False,
    )


def get_news_window(
    since: str | None = None,
    until: str | None = None,
    source_urls: list[str] | None = None,
    limit: int | None = None,
    cursor: str | None = None,
) -> dict[str, Any]:
    return _news_window_payload(
        since=since,
        until=until,
        source_urls=source_urls,
        limit=limit,
        cursor=cursor,
        include_entries=True,
    )


def _news_window_payload(
    *,
    since: str | None,
    until: str | None,
    source_urls: list[str] | None,
    limit: int | None,
    cursor: str | None,
    include_entries: bool,
) -> dict[str, Any]:
    since_dt, until_dt = _window_bounds(since, until)
    selected_sources = {url for url in (source_urls or []) if isinstance(url, str) and url.strip()}
    state = get_feed_state()
    entries: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []

    for source in state.sources:
        if selected_sources and source.source_url not in selected_sources:
            continue
        feed = state.feeds.get(source.source_url)
        source_entries = _entries_in_window(source, feed, since_dt, until_dt)
        sources.append(
            {
                **_source_payload(source, feed),
                "entry_count": len(source_entries),
            }
        )
        entries.extend(source_entries)

    entries.sort(key=lambda item: item.get("published_at") or "", reverse=True)
    offset = _parse_cursor(cursor)
    normalized_limit = _normalize_limit(limit)
    page_entries = entries[offset : offset + normalized_limit] if include_entries else []
    next_offset = offset + normalized_limit
    next_cursor = str(next_offset) if include_entries and next_offset < len(entries) else None
    return {
        "window": {"since": since_dt.isoformat(), "until": until_dt.isoformat()},
        "generated_at": datetime.now(UTC).isoformat(),
        "total": len(entries),
        "returned": len(page_entries),
        "next_cursor": next_cursor,
        "sources": sources,
        "entries": page_entries,
    }


def _entries_in_window(
    source: FeedSourceEntry,
    feed: FeedPreviewResponse | None,
    since_dt: datetime,
    until_dt: datetime,
) -> list[dict[str, Any]]:
    if feed is None:
        return []
    entries: list[dict[str, Any]] = []
    for item in feed.items:
        published_at = _item_published_at(item)
        if published_at is None or published_at < since_dt or published_at > until_dt:
            continue
        entries.append(
            {
                "id": item.id,
                "source_id": source.source_url,
                "source_url": source.source_url,
                "source_title": source.site_title,
                "title": item.title,
                "url": item.link,
                "summary": item.summary,
                "author": item.author,
                "published_at": published_at.isoformat(),
                "first_seen_at": None,
                "tags": list(item.tags or []),
            }
        )
    return entries


def _source_payload(source: FeedSourceEntry, feed: FeedPreviewResponse | None) -> dict[str, Any]:
    return {
        "source_id": source.source_url,
        "source_url": source.source_url,
        "site_title": source.site_title,
        "site_url": source.site_url,
        "description": source.description,
        "last_loaded_at": _dt_to_str(source.last_loaded_at),
        "last_refreshed_at": _dt_to_str(source.last_refreshed_at),
        "last_refresh_status": source.last_refresh_status,
        "last_refresh_error": source.last_refresh_error,
        "cached_entry_count": len(feed.items) if feed is not None else 0,
    }


def _window_bounds(since: str | None, until: str | None) -> tuple[datetime, datetime]:
    until_dt = _parse_datetime(until) if until else datetime.now(UTC)
    since_dt = _parse_datetime(since) if since else until_dt - timedelta(hours=24)
    if since_dt > until_dt:
        raise ValueError("since must be earlier than until")
    return since_dt, until_dt


def _parse_datetime(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _item_published_at(item: FeedPreviewItem) -> datetime | None:
    if item.published_at is None:
        return None
    return item.published_at.astimezone(UTC)


def _normalize_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_WINDOW_LIMIT
    try:
        value = int(limit)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be an integer") from exc
    if value < 1:
        return DEFAULT_WINDOW_LIMIT
    return min(value, MAX_WINDOW_LIMIT)


def _parse_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        value = int(cursor)
    except ValueError as exc:
        raise ValueError("cursor must be an integer offset") from exc
    return max(value, 0)


def _dt_to_str(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat()


def _tool_result(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}],
        "structuredContent": payload,
        "isError": False,
    }


def _json_rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "get_news_sources",
            "description": "列出 OneRadar 当前 RSS 新闻源、刷新状态和缓存数量。",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "get_news_window_status",
            "description": "返回指定时间窗口内每个新闻源的条目数量和刷新状态，不返回正文条目。",
            "inputSchema": _window_input_schema(include_pagination=False),
        },
        {
            "name": "get_news_window",
            "description": "返回指定时间窗口内的原始结构化新闻条目。默认窗口是调用时刻前 24 小时。",
            "inputSchema": _window_input_schema(include_pagination=True),
        },
    ]


def _window_input_schema(*, include_pagination: bool) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "since": {
            "type": "string",
            "description": "窗口开始时间，ISO 8601；不传则为 until 前 24 小时。",
        },
        "until": {"type": "string", "description": "窗口结束时间，ISO 8601；不传则为当前时间。"},
        "source_urls": {
            "type": "array",
            "items": {"type": "string"},
            "description": "可选，只返回这些 RSS 源 URL 的条目。",
        },
    }
    if include_pagination:
        properties["limit"] = {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_WINDOW_LIMIT,
            "description": f"返回条数上限，默认 {DEFAULT_WINDOW_LIMIT}。",
        }
        properties["cursor"] = {"type": "string", "description": "上一页返回的 next_cursor。"}
    return {"type": "object", "properties": properties, "additionalProperties": False}
