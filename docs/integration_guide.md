# OneRadar Integration Guide

Production base URL:

```text
https://oneradar.whiteone.cn:8112
```

## Authentication

Create an integration token in OneRadar:

```text
调用接口 -> 调用令牌 -> 创建令牌
```

Use the token as a bearer token:

```http
Authorization: Bearer ort_xxx
```

Recommended scopes:

- `mcp:read` for RSS/news access through MCP.
- `analysis:write` for temporary URL analysis.

## Health Check

```bash
curl https://oneradar.whiteone.cn:8112/api/health
```

## MCP News Source

Endpoint:

```text
POST https://oneradar.whiteone.cn:8112/api/mcp
```

MCP is served by the OneRadar API container. There is no separate MCP process to start.

### Initialize

```bash
curl -X POST "https://oneradar.whiteone.cn:8112/api/mcp" \
  -H "Authorization: Bearer <OneRadar integration token>" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'
```

### List Tools

```bash
curl -X POST "https://oneradar.whiteone.cn:8112/api/mcp" \
  -H "Authorization: Bearer <OneRadar integration token>" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
```

Current tools:

- `get_news_sources`: list RSS sources, refresh status, and cached counts.
- `get_news_window_status`: count entries by source for a time window.
- `get_news_window`: return raw structured RSS entries for a time window.
- `refresh_news`: refresh current user's RSS sources, wait for new-entry translation to finish, and return refresh status plus optional window entries.

### Get News Window

```bash
curl -X POST "https://oneradar.whiteone.cn:8112/api/mcp" \
  -H "Authorization: Bearer <OneRadar integration token>" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "get_news_window",
      "arguments": {
        "since": "2026-06-23T00:00:00+08:00",
        "until": "2026-06-24T00:00:00+08:00",
        "limit": 200
      }
    }
  }'
```

Use MCP for another AI project that needs OneRadar RSS/news data. OneRadar supplies source status plus Chinese-first entry payloads: `title`/`summary` are display fields, `original_title`/`original_summary` keep the source text, and `translated_title`/`translated_summary` expose persisted translations when available. The downstream project owns ranking, grouping, writing, and delivery.

### Refresh Then Read

Use `refresh_news` when the caller needs the latest RSS cache before reading news. The tool is synchronous: when it returns, RSS refresh has completed and new/changed entries have gone through the translation path.

```bash
curl -X POST "https://oneradar.whiteone.cn:8112/api/mcp" \
  -H "Authorization: Bearer <OneRadar integration token>" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 4,
    "method": "tools/call",
    "params": {
      "name": "refresh_news",
      "arguments": {
        "since": "2026-06-25T00:00:00+08:00",
        "until": "2026-06-25T08:30:00+08:00",
        "include_entries": true,
        "limit": 1000
      }
    }
  }'
```

Response fields:

- `ready`: `true` means the refresh attempt and translation pass are complete.
- `status`: `completed` or `completed_with_errors`.
- `refresh`: source refresh totals and per-source errors.
- `translation`: new-entry translation totals and status.
- `entries`: present only when `include_entries=true`; same shape as `get_news_window`.

## Temporary URL Analysis

Endpoint:

```text
POST https://oneradar.whiteone.cn:8112/api/analysis/url
```

Request:

```bash
curl -X POST "https://oneradar.whiteone.cn:8112/api/analysis/url" \
  -H "Authorization: Bearer <OneRadar integration token>" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com/article"}'
```

Response shape:

```json
{
  "source_url": "https://example.com/article",
  "final_url": "https://example.com/article",
  "platform": "web",
  "content_type": "article",
  "title": "Article title",
  "source_name": "Example",
  "author": null,
  "published_at": null,
  "original_text": "Clean extracted text...",
  "source_text_kind": "readable_text",
  "summary": "Chinese summary...",
  "summary_provider": "extractive",
  "model_name": null,
  "metadata": {},
  "fetched_at": "2026-06-24T08:00:00Z",
  "persisted": false
}
```

Current platform behavior:

- Web pages and WeChat article pages: readable-text extraction and summary.
- Bilibili: metadata and visible description summary.
- Douyin and Xiaohongshu: visible platform text and media metadata through the open-source `parsehub` parser. The endpoint does not download or save media.
- YouTube: recognized, but the full adapter is not connected yet.

## Daily News

For direct system-to-system news use, prefer MCP `get_news_window` because it accepts integration tokens and returns raw source entries.

The desktop daily-news REST endpoint is user-session oriented:

```text
GET /api/daily-news?date=YYYY-MM-DD
```

For external read-only sharing, create a public daily-news share link in the OneRadar UI and let the other project read that public URL.

## Recommended Prompt For Another AI Project

```text
Use OneRadar as the source of truth for RSS/news.

Base URL: https://oneradar.whiteone.cn:8112
MCP endpoint: POST /api/mcp
Temporary analysis endpoint: POST /api/analysis/url

When you need news, call MCP tool get_news_window with an explicit since/until window and paginate until next_cursor is null.
When you need to analyze a single URL, call /api/analysis/url and use original_text plus summary. Do not assume OneRadar saved the URL; persisted=false means it is temporary.
Use Authorization: Bearer <OneRadar integration token>.
Never ask OneRadar to store long-term notes; send useful outputs to Obsidian or the calling product.
```
