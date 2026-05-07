# OneRadar API V1

## 1. Scope

This document defines the V1 API surface for the OneRadar FastAPI backend.

The API is designed for a private, self-hosted deployment that serves a Windows desktop client first. The backend owns ingestion, parsing, transcription, summarization, provider management, search, annotations, and task orchestration.

V1 assumptions:

- Manual link input only.
- Supported link types in V1: article URLs and Bilibili video URLs.
- Bilibili processing is subtitle-first, ASR-second.
- Provider management is a first-class API surface.
- Single-user or small-private-deployment is the default operating model.

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

V1 is a single-user desktop reader and must not expose a user-facing account or login flow.

Recommended default:

- Desktop configures the server address and calls a workspace bootstrap endpoint.
- The backend keeps an internal primary user only as an ownership boundary for rows.
- API examples omit login and token headers in V1.
- If deployment-level protection is needed, put it outside the V1 product UX, for example behind a reverse proxy or local network boundary.

### 3.1 Workspace Bootstrap

Recommended V1 workspace endpoints:

- `GET /api/auth/bootstrap`
- `GET /api/auth/me`

`/api/auth/me` returns the internal primary user for diagnostics and ownership context. It is not a login session endpoint.

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
  "version": "v1",
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

## 6. Unified Import Flow

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
GET /api/feeds/preview?url=https://blog.python.org/rss.xml&limit=40
```

Returns feed metadata and recent entries without creating content items. Each entry includes `is_saved`, `saved_item_id`, and `saved_uid` when its article URL already exists in saved items. HN-style descriptions with explicit `Article URL` and `Comments URL` use the article URL as the entry link.

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

Persists the RSS discovery surface in the primary database. `POST /api/feeds/cache` upserts a loaded source and its current entries. `POST /api/feeds/read` marks a cached entry as read. `POST /api/feeds/refresh` refreshes all saved RSS sources server-side and returns `{ total, refreshed, failed, errors }`. `POST /api/feeds/sources/error` records a refresh failure without deleting the previous cached entries. Deleting a source removes its cached entries and read markers.

The API process also runs the same refresh logic on a timer when `ONERADAR_FEED_REFRESH_ENABLED=true`. The default interval is controlled by `ONERADAR_FEED_REFRESH_INTERVAL_SECONDS` and defaults to 1800 seconds.

The desktop 每日新闻 page currently reuses `GET /api/feeds/state` plus `POST /api/feeds/refresh`; it does not need a separate summary table or ingestion endpoint. The client applies a freshness window and lightweight topical grouping on cached RSS entries, then links entries back to `/feed/preview` or the source-level Feed page.

## 6.5 Direct API Use Cases

The desktop client is only one consumer of the backend. These endpoints are stable enough for local scripts or future integrations:

- Add an article link to 稍后阅读 and start parsing: `POST /api/items/import` with `{ "url": "...", "source_hint": "article" }`.
- Add a Bilibili video link to 稍后阅读 and start parsing: `POST /api/items/import` with `{ "url": "...", "source_hint": "bilibili_video" }`.
- Add a Bilibili video after preview: `POST /api/items/bilibili/preview`, then `POST /api/items/import`.
- List knowledge-library or inbox items: `GET /api/items?inbox_only=true&page=1&page_size=20` or `GET /api/items?folder_id={folder_id}`.
- Read a saved item with parsed text, summaries, transcript, tags, notes, and collections: `GET /api/items/{id}`.
- Soft-delete an item into 最近删除: `DELETE /api/items/{id}`. Deleted items are hidden from normal lists and retained for 7 days.
- List 最近删除: `GET /api/items/trash?page=1&page_size=100`.
- Restore or permanently purge a deleted item: `POST /api/items/trash/{id}/restore`, `DELETE /api/items/trash/{id}/purge`.
- List, create, rename, and delete folders: `GET /api/items/folders`, `POST /api/items/folders`, `PATCH /api/items/folders/{id}`, `DELETE /api/items/folders/{id}`.
- Move an item into a folder: `POST /api/items/{id}/move`.
- Trigger or retry AI summary generation for a saved item: `POST /api/items/{id}/summaries/generate`.
- Read or refresh RSS discovery state: `GET /api/feeds/state`, `POST /api/feeds/refresh`.

The current direct-add API intentionally covers articles and Bilibili videos. Podcast import still uses podcast-specific episode metadata because there is not yet a single user-facing podcast URL format that can represent a stable episode identity.

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

The Bilibili integration settings also include `visual_enhancement_enabled`. This flag is independent from Cookie enablement: when it is true, successful Bilibili import still uses subtitle-first/ASR-second text as the canonical transcript, then optionally runs visual frame analysis as a non-blocking enhancement.

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
