# OneRadar API V1

## 1. Scope

This document defines the V1 API surface for the OneRadar FastAPI backend.

The API is designed for a private, self-hosted deployment that serves a Windows desktop client first. After the 2026-06 scope reset, the primary API surface is RSS source state, daily news, temporary URL analysis, MCP/news handoff, integration tokens, and provider management.

V1 assumptions:

- RSS sources are user-managed and continuously refreshed.
- Daily news is generated from cached RSS entries.
- Temporary URL analysis accepts article/WeChat/web links and Bilibili metadata today, with YouTube/Douyin/Xiaohongshu adapters planned.
- Temporary URL analysis returns text, summary, and metadata without creating saved reading items.
- Provider management is a first-class API surface.
- Single-user or small-private-deployment is the default operating model.
- Legacy saved-item, reader, annotation, folder, collection, and podcast APIs may remain for data compatibility, but they are not primary product surfaces.

## 2. API Conventions

### 2.1 Base Path

All endpoints are rooted at:

```text
/api
```

### 2.2 Content Type

Requests and responses use JSON unless otherwise noted.

File upload endpoints, if added later, should use `multipart/form-data`. V1 should minimize file upload complexity.

### 2.3 Time Format

All timestamps use ISO 8601 in UTC, for example:

```json
"2026-04-13T08:30:00Z"
```

### 2.4 Pagination

List endpoints use one of these patterns:

- `page` and `page_size`
- cursor pagination only if a future implementation requires it

Recommended defaults:

- `page = 1`
- `page_size = 20`

### 2.5 Sorting

When needed, use explicit query parameters such as:

- `sort=created_at`
- `order=desc`

Do not rely on implicit ordering.

## 3. Single-User Workspace Model

V1 formal mode exposes a lightweight private-deployment account flow. Login and registration use username/email plus password. It is not a SaaS/team authorization model.

Recommended default:

- Desktop configures the server address and calls a workspace bootstrap endpoint.
- The backend keeps an internal primary user only as an ownership boundary for rows.
- Protected API examples require `Authorization: Bearer <token>`.
- If deployment-level protection is needed, put it outside the V1 product UX, for example behind a reverse proxy or local network boundary.

Service integrations should not reuse browser login tokens. Use user-created integration tokens instead: the logged-in user creates a token, the raw token is shown once, the server stores only its hash, and service calls resolve back to the token owner.

### 3.1 Workspace Bootstrap

Recommended V1 workspace endpoints:

- `GET /api/auth/bootstrap`
- `GET /api/auth/me`
- `POST /api/auth/login`
- `POST /api/auth/register`

`/api/auth/bootstrap` returns workspace and UI capability metadata without exposing secrets. `/api/auth/login` and `/api/auth/register` return a bearer token plus user profile. `/api/auth/me` returns the authenticated user.

### 3.2 Bootstrap Response

```json
{
  "workspace_name": "OneRadar",
  "single_user_mode": true,
  "ui_locale": "zh-CN",
  "requires_login": false,
  "default_inbox_folder": {
    "id": "uuid",
    "name": "稍后阅读",
    "is_builtin": true,
    "item_count": 0
  },
  "primary_user": {
    "id": "uuid",
    "username": "local"
  }
}
```

### 3.3 Integration Tokens

Integration tokens are personal access tokens for service-to-service use, such as Hermes calling OneRadar MCP or another product calling temporary URL analysis. They are bound to the user who creates them and are not default-mapped to a hard-coded account.

```http
GET /api/integration-tokens
POST /api/integration-tokens
DELETE /api/integration-tokens/{token_id}
```

Create request:

```json
{
  "name": "OneRadar API",
  "scopes": ["mcp:read", "analysis:write"]
}
```

Create response:

```json
{
  "item": {
    "id": "uuid",
    "name": "OneRadar API",
    "token_prefix": "ort_xxxxxxxx",
    "scopes": ["mcp:read", "analysis:write"],
    "created_at": "2026-05-13T08:30:00Z",
    "last_used_at": null,
    "revoked_at": null
  },
  "token": "ort_full_token_shown_once"
}
```

List responses never include the raw `token`; they only include metadata and `token_prefix`. Deleting a token revokes it.

## 4. Error Format

All non-2xx responses should follow a consistent error shape.

```json
{
  "error": {
    "code": "invalid_argument",
    "message": "url is required",
    "details": {
      "field": "url"
    },
    "request_id": "req_01J..."
  }
}
```

### 4.1 Suggested Error Codes

- `unauthorized`
- `forbidden`
- `not_found`
- `conflict`
- `invalid_argument`
- `unprocessable_entity`
- `rate_limited`
- `external_dependency_failed`
- `task_failed`
- `internal_error`

### 4.2 Status Code Guidance

- `400` for malformed input.
- `401` for missing/invalid auth.
- `403` for permitted auth but disallowed action.
- `404` for missing resources.
- `409` for duplicate or conflicting state.
- `422` for structurally valid but semantically invalid input.
- `500` for unexpected server failure.

## 5. Health and Meta

### 5.1 Health Check

```http
GET /api/health
```

Response:

```json
{
  "status": "ok",
  "version": "1.0.0",
  "time": "2026-04-13T08:30:00Z"
}
```

### 5.2 Current User

```http
GET /api/auth/me
```

Response:

```json
{
  "id": "uuid",
  "username": "admin",
  "created_at": "2026-04-13T08:30:00Z"
}
```

## 6. Temporary URL Analysis

Temporary analysis is the primary direct-call surface for pasted links. It is intentionally non-persistent: the endpoint returns source text or visible platform text, summary, metadata, and JSON in one response, but it does not create `content_items`, reading state, folders, notes, highlights, or collection records.

```http
POST /api/analysis/url
Authorization: Bearer <login token or integration token with analysis:write>
Content-Type: application/json
```

Request:

```json
{
  "url": "https://example.com/article",
  "platform_hint": "web"
}
```

Response:

```json
{
  "source_url": "https://example.com/article",
  "final_url": "https://example.com/article",
  "platform": "web",
  "content_type": "article",
  "title": "Article title",
  "source_name": "Example",
  "author": "Author",
  "published_at": "2026-06-24T08:30:00Z",
  "original_text": "Clean text visible to OneRadar...",
  "source_text_kind": "readable_text",
  "summary": "Chinese summary generated by the configured summarization model or extractive fallback.",
  "summary_provider": "Doubao",
  "model_name": "doubao-chat",
  "metadata": {
    "parser_name": "feed-preview"
  },
  "fetched_at": "2026-06-24T08:31:00Z",
  "persisted": false
}
```

Current behavior:

- Web pages and WeChat article URLs use the existing article extraction path and return `source_text_kind=readable_text`.
- Bilibili URLs return video metadata and visible description as `source_text_kind=metadata_description`; full subtitle/transcript analysis remains adapter work.
- YouTube, Douyin, and Xiaohongshu URLs are recognized but return a clear “adapter not connected” error until platform-specific extractors are implemented.
- If no summarization provider is configured, the endpoint returns an extractive summary and `summary_provider=extractive`.

## 7. Legacy Unified Import Flow

The legacy import flow is kept for data compatibility and older clients. It is no longer the primary OneRadar product path after the 2026-06 reset.

V1 exposes a single import entrypoint for article and Bilibili URLs. Podcast episodes are imported through the podcast API because their identity comes from RSS episode metadata, not only from a pasted URL.

### 6.1 Preview Bilibili Video

The Bilibili desktop surface may preview video metadata before creating a reading item. Preview is intentionally read-only: it fetches title, cover, owner, duration, IDs, and a normalized URL, but does not create a `content_item` or enqueue AI/transcription work.

```http
POST /api/items/bilibili/preview
Content-Type: application/json
```

Request:

```json
{
  "url": "https://www.bilibili.com/video/BV1xxxxxxx"
}
```

Response:

```json
{
  "content_type": "bilibili_video",
  "source_url": "https://www.bilibili.com/video/BV1xxxxxxx",
  "normalized_url": "https://www.bilibili.com/video/BV1xxxxxxx/",
  "title": "视频标题",
  "owner_name": "UP 主",
  "cover_url": "https://i0.hdslb.com/...",
  "duration_seconds": 1234,
  "duration_text": "20:34",
  "bvid": "BV1xxxxxxx",
  "aid": 123,
  "cid": 456,
  "subtitle_status": "确认加入后检测字幕"
}
```

The client should call the import endpoint only after the user confirms the preview is the intended video.

### 6.2 Create Import Task

```http
POST /api/items/import
Content-Type: application/json
```

Request:

```json
{
  "url": "https://example.com/article",
  "source_hint": "article",
  "title": "Optional preview title",
  "site_title": "Optional RSS source",
  "author": "Optional author",
  "published_at": "2026-04-30T08:30:00Z",
  "summary": "Optional RSS summary",
  "parsed_text": "Optional cleaned reader text from preview",
  "parser_name": "feed-preview",
  "parser_version": "v1",
  "generate_summary": true
}
```

`source_hint` is optional. If omitted, the backend infers the source from the URL. The optional preview fields are used by RSS preview saves so the backend can persist the already-cleaned reader text immediately and queue AI summary generation only after an explicit save.

Response:

```json
{
  "item_id": "uuid",
  "task_id": "uuid",
  "status": "pending",
  "content_type": "bilibili_video"
}
```

### 6.2 Import Behavior

The backend should:

1. Normalize the URL.
2. Check for duplicates.
3. Create a `content_item`.
4. Enqueue the appropriate processing pipeline.
5. Return a task-backed response immediately.

If the URL already exists, return the existing item and a non-fatal status instead of creating duplicates. The API should use `content_type` to mirror the database field name `content_items.content_type`.

Example conflict-safe response:

```json
{
  "item_id": "uuid",
  "task_id": "uuid",
  "status": "already_exists",
  "content_type": "article"
}
```

## 7. Item APIs

### 7.1 List Items

```http
GET /api/items?keyword=reader&tag=knowledge&page=1&page_size=20
```

Response:

```json
{
  "items": [
    {
      "id": "uuid",
      "title": "Example Article",
      "content_type": "article",
      "source_url": "https://example.com/article",
      "status": "completed",
      "is_read": false,
      "is_favorited": false,
      "created_at": "2026-04-13T08:30:00Z",
      "updated_at": "2026-04-13T08:35:00Z"
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1
}
```

### 7.2 Get Item Detail

```http
GET /api/items/{id}
```

Response:

```json
{
  "id": "uuid",
  "title": "Example Article",
  "content_type": "article",
  "source_url": "https://example.com/article",
  "status": "completed",
  "metadata": {
    "author_name": "Author",
    "published_at": "2026-04-12T10:00:00Z",
    "site_name": "Example"
  },
  "parsed_document": {
    "plain_text": "Readable article text...",
    "structured_blocks": []
  },
  "transcript": null,
  "summaries": [],
  "highlights": [],
  "notes": [],
  "tags": [],
  "collections": [],
  "reading_state": {
    "progress_percent": 0,
    "last_read_at": null,
    "is_archived": false,
    "is_favorited": false
  }
}
```

### 7.3 Reprocess Item

```http
POST /api/items/{id}/reprocess
```

Request:

```json
{
  "steps": ["extract", "transcribe", "summarize", "index"]
}
```

Response:

```json
{
  "item_id": "uuid",
  "task_id": "uuid",
  "status": "queued"
}
```

### 7.4 Generate Item Summary

```http
POST /api/items/{id}/summaries/generate
```

Creates a `generate_summary` task for the item. The worker resolves the enabled summarization provider, reads the best available source text from parsed article text, transcript text, or podcast episode summary, and persists a refreshed `short` summary.

Response:

```json
{
  "item_id": "uuid",
  "task_id": "uuid",
  "status": "pending"
}
```

## 8. Reading and Content Assets

### 8.1 Parsed Document

```http
GET /api/items/{id}/document
```

Response:

```json
{
  "id": "uuid",
  "plain_text": "Readable article text...",
  "structured_blocks": [],
  "parser_name": "trafilatura",
  "parser_version": "1.0"
}
```

### 8.2 Transcript

```http
GET /api/items/{id}/transcript
```

Response:

```json
{
  "id": "uuid",
  "transcript_type": "asr",
  "language": "zh",
  "full_text": "Transcribed text...",
  "segments": [
    {
      "start_ms": 0,
      "end_ms": 5200,
      "text": "hello world"
    }
  ]
}
```

### 8.3 Summaries

```http
GET /api/items/{id}/summaries
```

Response:

```json
{
  "items": [
    {
      "summary_type": "one_line",
      "content": "Short conclusion.",
      "model_name": "doubao-xxx",
      "version": 1
    }
  ]
}
```

### 8.4 Related Items

```http
GET /api/items/{id}/related
```

Response:

```json
{
  "items": []
}
```

## 9. Task APIs

### 9.1 List Tasks

```http
GET /api/tasks?status=failed&page=1&page_size=20
```

Response:

```json
{
  "items": [
    {
      "id": "uuid",
      "item_id": "uuid",
      "task_type": "transcribe_audio",
      "status": "failed",
      "attempt_count": 2,
      "error_message": "provider timeout",
      "created_at": "2026-04-13T08:30:00Z"
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1
}
```

### 9.2 Get Task

```http
GET /api/tasks/{id}
```

### 9.3 Retry Task

```http
POST /api/tasks/{id}/retry
```

Response:

```json
{
  "task_id": "uuid",
  "status": "retrying"
}
```

## 10. Provider APIs

Provider management is a core V1 API surface.

The provider list is user-created. Presets are only UI/API hints; they do not create default provider records. A saved provider must be complete for its capability: LLM providers require `base_url`, `api_key`, and `chat_model`; ASR providers require APP ID, resource/model ID, Access Token, and Secret Key. When a provider is saved or updated with `is_enabled=true`, it becomes the only enabled provider for that capability, so LLM and ASR selection stay independent.

### 10.1 List Providers

```http
GET /api/providers
```

Response:

```json
{
  "items": [
    {
      "id": "uuid",
      "provider_name": "Doubao",
      "provider_type": "doubao",
      "base_url": "https://api.example.com",
      "api_key_configured": true,
      "chat_model": "doubao-chat",
      "embedding_model": "doubao-embed",
      "transcription_model": "doubao-transcribe",
      "is_enabled": true
    }
  ]
}
```

### 10.2 Create Provider

```http
POST /api/providers
Content-Type: application/json
```

Request:

```json
{
  "provider_name": "Custom OpenAI Compatible",
  "provider_type": "openai_compatible",
  "base_url": "https://api.example.com/v1",
  "api_key": "sk-***",
  "chat_model": "gpt-4o-mini",
  "embedding_model": "text-embedding-3-small",
  "transcription_model": "gpt-4o-mini-transcribe",
  "is_enabled": true
}
```

Response:

```json
{
  "id": "uuid",
  "provider_name": "Custom OpenAI Compatible",
  "provider_type": "openai_compatible",
  "api_key_configured": true,
  "is_enabled": true
}
```

## 6.3 Podcast APIs

Podcast subscriptions are a scoped RSS exception. Subscribing only discovers episodes; it never downloads audio or triggers AI processing.

```http
GET /api/podcasts/search?q=凹凸电波&country=US&limit=12
```

Searches Apple iTunes Search API and returns podcast results with `feed_url` when Apple exposes one.

```http
GET /api/podcasts/subscriptions
POST /api/podcasts/subscriptions
DELETE /api/podcasts/subscriptions/{subscription_id}
```

Manages user podcast RSS subscriptions.

```http
GET /api/podcasts/episodes?limit=80
```

Aggregates episodes from subscribed RSS feeds, sorted by publish time descending.

```http
POST /api/podcasts/episodes/import
```

Creates a `podcast_episode` content item in Inbox / later reading. The request includes feed URL, episode title, GUID, publish time, enclosure URL, and optional enclosure metadata. Dedupe is based on feed URL plus GUID, falling back to enclosure URL. Only this explicit import step may download and persist audio.

## 6.4 RSS Preview APIs

RSS subscriptions are a discovery surface, not an automatic ingestion path.

```http
GET /api/feeds/preview?url=https://blog.python.org/rss.xml&limit=0
```

Returns feed metadata and entries without creating content items. `limit=0` means no entry-count truncation and is the formal default for subscribed sources; positive `limit` values are only for explicit previews or diagnostics. Each entry includes `is_saved`, `saved_item_id`, and `saved_uid` when its article URL already exists in saved items. HN-style descriptions with explicit `Article URL` and `Comments URL` use the article URL as the entry link.

```http
GET /api/feeds/article-preview?url=https://example.com/post&title=Fallback
```

Fetches a single RSS article URL and returns a transient clean reader preview. This endpoint does not create a `content_item` and does not enqueue parsing or AI tasks. It returns `is_saved`, `saved_item_id`, `saved_uid`, and `can_generate_ai=true` only when the URL already exists as a saved item. The desktop client should call `POST /api/items/import` only when the user explicitly adds the article to 稍后阅读.

```http
GET /api/feeds/state
POST /api/feeds/cache
POST /api/feeds/read
POST /api/feeds/refresh
POST /api/feeds/sources/error
DELETE /api/feeds/sources?url=https://blog.python.org/rss.xml
```

Persists the RSS discovery surface in the primary database. `POST /api/feeds/cache` upserts a loaded source and every fetched entry. Existing cached entries remain even if a later feed response no longer includes them, so source history accumulates until the source is deleted. `POST /api/feeds/read` marks a cached entry as read. `POST /api/feeds/refresh` refreshes all saved RSS sources server-side and returns `{ total, refreshed, failed, errors }`. `POST /api/feeds/sources/error` records a refresh failure without deleting the previous cached entries. Deleting a source removes its cached entries and read markers.

The API process also runs the same refresh logic on a timer when `ONERADAR_FEED_REFRESH_ENABLED=true`. The default interval is controlled by `ONERADAR_FEED_REFRESH_INTERVAL_SECONDS` and defaults to 1800 seconds.

The desktop 每日新闻 page is model-generated and persisted per date. The API reads cached RSS entries from the 24 hours before the actual generation time, calls the configured summarization/chat provider, asks the model to translate and summarize entries into a fixed daily-brief structure, and saves exactly one report per day. The generated structure is AI-first: the headline and lead must prefer AI news when available, the first section must be AI, AI coverage should be heavier than other sections, and game news belongs at the end. Regenerating the same date overwrites the previous report.

```http
GET /api/daily-news?date=2026-05-07
```

Returns the saved daily report for a date. If it has not been generated, the response uses `status: "missing"` so the client can show a generation action.

```http
POST /api/daily-news/share
```

Request body:

```json
{ "date": "2026-05-07" }
```

Creates or reuses a stable opaque `share_key` for the authenticated user and a per-report `share_id` for compatibility. New share URLs should use `share_key + date`, so the same URL continues to point at that user's latest saved report for the date after regeneration.

```http
GET /api/public/daily-news/users/{share_key}/2026-05-07
```

Returns the saved daily report for a valid user share key and date without requiring desktop authentication. This endpoint is read-only and exists only for public share pages that render the daily brief content without source-management, save-to-Inbox, date navigation, or regeneration controls. Different users sharing the same date have different `share_key` values.

```http
POST /api/daily-news/generate
```

Request body:

```json
{ "date": "2026-05-07", "force": true }
```

Generates or regenerates the report for the date. If a report already exists and `force` is not set, the API returns 409 because regeneration replaces the existing daily version. The API process also schedules automatic generation at `ONERADAR_DAILY_NEWS_GENERATION_HOUR`, defaulting to 10:00 in `Asia/Shanghai`.

## 6.5 Hermes MCP News Source

OneRadar exposes a built-in MCP endpoint from the same API container. It is intentionally not a separate Docker service because it reads the same persisted RSS state as the desktop and REST API.

```http
POST /api/mcp
```

The endpoint accepts JSON-RPC 2.0 MCP-style requests. The initial tools are:

- `get_news_sources`: returns configured RSS sources, refresh status, refresh errors, and cached entry counts.
- `get_news_window_status`: returns per-source counts for a time window without returning entries.
- `get_news_window`: returns raw structured RSS entries for a time window. `since` and `until` are ISO 8601 strings; if omitted, the default window is the previous 24 hours. `limit` defaults to 1000 and supports `next_cursor` pagination.

MCP accepts either a normal user bearer token or a user-created integration token with `mcp:read` scope. Hermes should use an integration token:

```http
Authorization: Bearer ort_...
```

The MCP handoff is a data-source boundary for Hermes Agent. OneRadar provides complete source entries and source status for the requested window; Hermes owns AI grouping, ranking, narration, and delivery. This keeps missing-news responsibility explicit: if an entry is present in `get_news_window`, any omission is downstream of OneRadar.

Recommended Hermes MCP configuration:

```json
{
  "mcpServers": {
    "oneradar-news": {
      "url": "http://192.168.100.55:8081/api/mcp",
      "headers": {
        "Authorization": "Bearer <OneRadar integration token>"
      }
    }
  }
}
```

Recommended Hermes morning-news instruction:

```text
每天早上生成 AI 早报时，必须优先调用 OneRadar MCP 的 get_news_window 工具获取新闻数据源。

默认时间窗口：
- since: 昨天 08:30 北京时间
- until: 今天 08:30 北京时间
- limit: 1000

如果 get_news_window 返回 next_cursor，继续翻页，直到 next_cursor 为 null。

责任边界：
- OneRadar MCP 返回的是完整原始新闻数据源。
- Hermes 负责筛选、去重、归类、排序、总结和播报。
- 不要声称数据源缺失，除非 get_news_window_status 或 get_news_sources 明确显示对应源刷新失败或窗口内 entry_count 为 0。

优先关注：
- AI 模型发布
- OpenAI / Anthropic / Google / Meta / xAI / DeepSeek / 字节 / 阿里 / 腾讯等大模型动态
- AI 产品更新
- Agent、语音、多模态、算力、Infra、机器人
- 中国 AI 生态
- 对白老师值得关注的产业或开发者事件

输出格式：
📰 AI 早报 | YYYY年M月D日 周X 08:30 北京时间

🔥 今日 Top 3
每条包含：标题、一段中文总结、📎 来源：来源名

📦 产品 & 模型更新
条目列表

🏗️ 产业 & 算力动态
条目列表

🌏 中国 AI 生态
条目列表

⚡ 值得白老师关注
要点列表

📡 数据源：
OneRadar MCP，列出主要来源和时间窗口。
```

## 6.6 Direct API Use Cases

The desktop client is only one consumer of the backend. These endpoints are stable enough for local scripts or future integrations:

- Analyze a webpage or WeChat article without saving it: `POST /api/analysis/url` with `{ "url": "..." }`.
- Analyze a Bilibili URL without saving it: `POST /api/analysis/url` with `{ "url": "...", "platform_hint": "bilibili" }`.
- Read or refresh RSS discovery state: `GET /api/feeds/state`, `POST /api/feeds/refresh`.
- Generate or read a daily report: `POST /api/daily-news/generate`, `GET /api/daily-news?date=YYYY-MM-DD`.
- Expose raw news entries to agents through MCP: `POST /api/mcp` with an integration token carrying `mcp:read`.
- Call temporary URL analysis from another product with an integration token carrying `analysis:write`.

Legacy saved-item, folder, reading-state, annotation, collection, and podcast import APIs are retained only for compatibility with older data and clients. New UI and new integrations should use temporary analysis plus external knowledge storage, for example Obsidian.

Provider API responses must never echo raw API keys. The server stores provider keys in `api_key_encrypted` and only exposes `api_key_configured` to the client.

### 10.3 Update Provider

```http
PUT /api/providers/{id}
```

### 10.4 Delete Provider

```http
DELETE /api/providers/{id}
```

### 10.5 Test Provider Connection

```http
POST /api/providers/{id}/test
```

Response:

```json
{
  "ok": true,
  "latency_ms": 420
}
```

### 10.6 Provider Presets

```http
GET /api/providers/presets
```

Response:

```json
{
  "items": [
    {
      "provider_type": "doubao",
      "provider_name": "Doubao"
    },
    {
      "provider_type": "deepseek",
      "provider_name": "DeepSeek"
    },
    {
      "provider_type": "openai_compatible",
      "provider_name": "OpenAI Compatible"
    }
  ]
}
```

## 11. Search APIs

### 11.1 Search Items

```http
GET /api/search?q=whisper&page=1&page_size=20
```

Response:

```json
{
  "items": [
    {
      "id": "uuid",
      "title": "Example Article",
      "content_type": "article",
      "snippets": [
        "matching snippet..."
      ],
      "score": 0.92
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1
}
```

### 11.2 Search Suggestions

```http
GET /api/search/suggestions?q=whis
```

Response:

```json
{
  "items": ["whisper", "whisperx", "faster-whisper"]
}
```

## 12. Annotation APIs

Annotations are first-class objects, not UI-only state.

### 12.1 Create Highlight

```http
POST /api/items/{id}/highlights
```

Request:

```json
{
  "quote_text": "important sentence",
  "start_anchor": "p3",
  "end_anchor": "p3",
  "color": "yellow"
}
```

Response:

```json
{
  "id": "uuid",
  "item_id": "uuid",
  "quote_text": "important sentence",
  "anchor_type": "article_text",
  "start_anchor": "p3",
  "end_anchor": "p3",
  "start_offset": null,
  "end_offset": null,
  "segment_index": null,
  "color": "yellow",
  "note_id": null
}
```

### 12.2 List Highlights

```http
GET /api/items/{id}/highlights
```

### 12.3 Create Note

```http
POST /api/items/{id}/notes
```

Request:

```json
{
  "highlight_id": "uuid",
  "content": "My note"
}
```

### 12.4 Update Note

```http
PUT /api/notes/{id}
```

Request:

```json
{
  "content": "Updated note"
}
```

### 12.5 Delete Note

```http
DELETE /api/notes/{id}
```

Response:

```json
{
  "id": "uuid",
  "deleted": true
}
```

### 12.6 Tags

```http
POST /api/items/{id}/tags
```

Request:

```json
{
  "tags": ["research", "video"]
}
```

Response:

```json
{
  "items": [
    { "id": "research", "name": "research" },
    { "id": "video", "name": "video" }
  ]
}
```

## 13. Collections APIs

### 13.1 Create Collection

```http
POST /api/collections
```

Request:

```json
{
  "name": "AI Reading",
  "description": "Saved materials about AI"
}
```

### 13.2 List Collections

```http
GET /api/collections
```

Response:

```json
{
  "items": [
    {
      "id": "uuid",
      "name": "AI Reading",
      "description": "Saved materials about AI",
      "is_favorite": false,
      "item_count": 3
    }
  ]
}
```

### 13.3 Get Collection

```http
GET /api/collections/{id}
```

### 13.4 Add Item to Collection

```http
POST /api/collections/{id}/items
```

Request:

```json
{
  "item_id": "uuid"
}
```

Response:

```json
{
  "id": "uuid",
  "name": "AI Reading",
  "item_count": 4
}
```

### 13.5 Remove Item from Collection

```http
DELETE /api/collections/{id}/items/{item_id}
```

Response:

```json
{
  "id": "uuid",
  "name": "AI Reading",
  "item_count": 3
}
```

## 14. Reading State APIs

### 14.1 Update Reading State

```http
PUT /api/items/{id}/reading-state
```

Request:

```json
{
  "progress_percent": 42,
  "is_archived": false,
  "is_favorited": true
}
```

### 14.2 Mark Read/Unread

If needed, the UI can use the same reading-state endpoint rather than separate read/unread endpoints.

## 15. Settings APIs

### 15.1 Get Bilibili Integration Settings

```http
GET /api/settings/integrations/bilibili
```

Response should return:

- enabled state
- whether `SESSDATA`, `bili_jct`, and `buvid3` are configured
- masked previews only
- whether the saved cookie set is ready for authenticated subtitle fetch

For QR-code login, readiness is based on `SESSDATA` plus `bili_jct`; `buvid3` remains useful when imported from a browser but is not required because Bilibili Web QR login may not return it.

Multimodal video/audio analysis is not controlled by a Bilibili-specific toggle. It is driven by the enabled LLM provider's input capability flags: video, image, and audio inputs can trigger sampled video, sampled frame, or extracted-audio analysis, with subtitle text included as prompt context and ASR kept as fallback.

### 15.2 Update Bilibili Integration Settings

```http
PUT /api/settings/integrations/bilibili
```

Example request:

```json
{
  "is_enabled": true,
  "cookie_header": "SESSDATA=...; bili_jct=...; buvid3=..."
}
```

Notes:

- The client may also send `sessdata`, `bili_jct`, and `buvid3` individually.
- API responses must never echo raw cookie values.
- Omitting a field should preserve the stored value; sending an empty string should clear it.

### 15.3 Parse Bilibili Cookie Header

```http
POST /api/settings/integrations/bilibili/parse-cookie
```

Use this for import-page previews when the user pastes a full browser cookie string and wants to verify which fields can be extracted before saving.

### 15.4 Create Bilibili QR Login

```http
POST /api/settings/integrations/bilibili/qrcode
```

Response:

```json
{
  "url": "https://passport.bilibili.com/h5-app/passport/login/scan?...",
  "qrcode_key": "32-character-key",
  "expires_in_seconds": 180
}
```

The desktop client renders `url` as a local QR code and keeps `qrcode_key` only for polling. Do not persist the QR URL or key as integration credentials.

### 15.5 Poll Bilibili QR Login

```http
POST /api/settings/integrations/bilibili/qrcode/poll
```

Request:

```json
{
  "qrcode_key": "32-character-key"
}
```

Response:

```json
{
  "code": 86090,
  "state": "scanned",
  "message": "已扫码，等待确认",
  "saved_cookie": null
}
```

State values:

- `waiting`: not scanned yet
- `scanned`: scanned but not confirmed on the phone
- `confirmed`: login confirmed and server-side integration cookies saved
- `expired`: QR code expired
- `failed`: polling failed or returned an unexpected state

On `confirmed`, the API stores any returned Bilibili cookies through the existing integration settings path and returns only the masked settings object in `saved_cookie`.

## 16. Task-Oriented Flows

### 16.1 Article Import Flow

1. Desktop client sends `POST /api/items/import`.
2. Backend normalizes the URL and creates or reuses the item.
3. Worker fetches HTML.
4. Parser extracts metadata and readable body.
5. Summary job runs after readable text exists.
6. Index job makes the item searchable.
7. Client polls `GET /api/items/{id}` or `GET /api/tasks/{id}` until processing is complete.

### 16.2 Bilibili Import Flow

1. Desktop client sends `POST /api/items/import`.
2. Backend identifies the URL as Bilibili.
3. Worker fetches metadata.
4. Worker tries subtitles first.
5. If subtitles are unavailable, worker extracts audio and transcribes.
6. Transcript is stored with timestamped segments.
7. Summary and outline are generated.
8. Client opens the item and can jump by timestamp.

Implementation note:

- ASR uses the enabled provider with a configured `transcription_model`.
- Task results may include provider/model names and `transcript_type = "asr"`, but must not include raw provider API keys.

### 16.3 Failed Task Recovery Flow

1. User opens a failed item or task.
2. Client calls `POST /api/tasks/{id}/retry` or `POST /api/items/{id}/reprocess`.
3. Backend creates a new task instance or requeues the existing one.
4. Client continues polling until success or failure.

## 17. Implementation Notes

- Keep item import synchronous only for task creation, not for full parsing.
- Never block the API request on transcription or summarization work.
- Do not expose provider secrets in API responses.
- Do not create separate import endpoints for article and Bilibili in V1 unless the unified flow becomes unworkable.
- If a resource can be represented as a task, prefer a task-backed API.

## 18. Future Extensions

Not part of V1, but the API design should leave room for:

- PDF import and parsing.
- Local file uploads.
- RSS ingestion.
- Semantic search.
- Mobile client support.
- Multi-user authorization models.
