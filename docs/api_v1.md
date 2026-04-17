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

## 3. Authentication Model

V1 should use a simple private-deployment auth model.

Recommended default:

- Login returns an access token.
- Client sends `Authorization: Bearer <token>`.
- Token storage is handled by the desktop client.

Alternative server-managed session cookies are acceptable if the UI is ever served directly from the backend, but the desktop-first API should not depend on browser cookies.

### 3.1 Login Flow

Recommended V1 auth endpoints:

- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`

### 3.2 Login Request

```http
POST /api/auth/login
Content-Type: application/json
```

```json
{
  "username": "admin",
  "password": "secret"
}
```

### 3.3 Login Response

```json
{
  "access_token": "eyJhbGciOi...",
  "token_type": "Bearer",
  "expires_in": 86400,
  "user": {
    "id": "uuid",
    "username": "admin"
  }
}
```

### 3.4 Auth Headers

```http
Authorization: Bearer eyJhbGciOi...
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

V1 should expose a single import entrypoint for both article and Bilibili URLs.

### 6.1 Create Import Task

```http
POST /api/items/import
Content-Type: application/json
Authorization: Bearer <token>
```

Request:

```json
{
  "url": "https://www.bilibili.com/video/BV1xxxxxxx",
  "source_hint": "bilibili"
}
```

`source_hint` is optional. If omitted, the backend infers the source from the URL.

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
Authorization: Bearer <token>
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
Authorization: Bearer <token>
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
Authorization: Bearer <token>
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

## 8. Reading and Content Assets

### 8.1 Parsed Document

```http
GET /api/items/{id}/document
Authorization: Bearer <token>
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
Authorization: Bearer <token>
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
Authorization: Bearer <token>
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
Authorization: Bearer <token>
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
Authorization: Bearer <token>
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
Authorization: Bearer <token>
```

### 9.3 Retry Task

```http
POST /api/tasks/{id}/retry
Authorization: Bearer <token>
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
Authorization: Bearer <token>
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
Authorization: Bearer <token>
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
  "is_enabled": true
}
```

### 10.3 Update Provider

```http
PUT /api/providers/{id}
Authorization: Bearer <token>
```

### 10.4 Delete Provider

```http
DELETE /api/providers/{id}
Authorization: Bearer <token>
```

### 10.5 Test Provider Connection

```http
POST /api/providers/{id}/test
Authorization: Bearer <token>
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
Authorization: Bearer <token>
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
Authorization: Bearer <token>
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
Authorization: Bearer <token>
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
Authorization: Bearer <token>
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
  "item_id": "uuid"
}
```

### 12.2 List Highlights

```http
GET /api/items/{id}/highlights
Authorization: Bearer <token>
```

### 12.3 Create Note

```http
POST /api/items/{id}/notes
Authorization: Bearer <token>
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
Authorization: Bearer <token>
```

### 12.5 Delete Note

```http
DELETE /api/notes/{id}
Authorization: Bearer <token>
```

### 12.6 Tags

```http
POST /api/items/{id}/tags
Authorization: Bearer <token>
```

Request:

```json
{
  "tags": ["research", "video"]
}
```

## 13. Collections APIs

### 13.1 Create Collection

```http
POST /api/collections
Authorization: Bearer <token>
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
Authorization: Bearer <token>
```

### 13.3 Get Collection

```http
GET /api/collections/{id}
Authorization: Bearer <token>
```

### 13.4 Add Item to Collection

```http
POST /api/collections/{id}/items
Authorization: Bearer <token>
```

Request:

```json
{
  "item_id": "uuid"
}
```

### 13.5 Remove Item from Collection

```http
DELETE /api/collections/{id}/items/{item_id}
Authorization: Bearer <token>
```

## 14. Reading State APIs

### 14.1 Update Reading State

```http
PUT /api/items/{id}/reading-state
Authorization: Bearer <token>
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
Authorization: Bearer <token>
```

Response should return:

- enabled state
- whether `SESSDATA`, `bili_jct`, and `buvid3` are configured
- masked previews only
- whether the saved cookie set is ready for authenticated subtitle fetch

### 15.2 Update Bilibili Integration Settings

```http
PUT /api/settings/integrations/bilibili
Authorization: Bearer <token>
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
Authorization: Bearer <token>
```

Use this for import-page previews when the user pastes a full browser cookie string and wants to verify which fields can be extracted before saving.

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
