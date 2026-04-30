# OneRadar Implementation TODO

## How To Maintain This File

This is the persistent build checklist for the repo.

Rules:

- Use Markdown checkboxes.
- Only tick a task when the implementation is actually merged into the working tree and verified at an appropriate level.
- If a task is partially done, add a short note beneath it in plain text instead of checking it.
- When new work appears, add it in the correct priority section instead of creating scattered TODO files.

Legend:

- `P0`: critical path for usable V1.
- `P1`: important but not required for first closed loop.
- `P2`: later enhancements.

---

## P0 Product Corrections

- [x] Remove user-facing login/account flow from desktop and backend UX.
- [x] Convert desktop UI copy to Chinese-first.
- [x] Add Inbox as the default landing state for newly imported items.
- [x] Add folder system and item move-to-folder flow.
- [x] Add theme mode support: light / dark / follow system.
- [x] Expose stable item UID in item list/detail/import responses and duplicate-import responses.

---

## P0 Product And Architecture

- [x] Rewrite V1 PRD around manual link input, reader-first UX, and Bilibili transcription support.
- [x] Define reusable references, component landscape, and repo engineering constraints.
- [x] Write `docs/architecture_v1.md`.
- [x] Write `docs/database_v1.md`.
- [x] Write `docs/api_v1.md`.
- [ ] Decide initial monorepo package boundaries.
- [x] Decide provider abstraction interfaces.
- [x] Decide Docker Compose baseline services.

## P0 Repo Bootstrap

- [x] Scaffold repo directories under `apps/`, `packages/`, and `infra/`.
- [x] Initialize backend service skeleton.
- [x] Initialize worker service skeleton.
- [x] Initialize desktop client skeleton.
- [x] Add shared config and environment loading.
- [ ] Add root-level scripts for local development.
- [ ] Add formatting, linting, and type-check commands.

## P0 Backend Foundations

- [x] Implement health check and authenticated user bootstrap path.
- [x] Implement database connection and migration baseline.
- [x] Implement `content_items` core model.
- [x] Implement `content_snapshots` model.
- [x] Implement `content_parsed_documents` model.
- [x] Implement `transcripts` model.
- [x] Implement `summaries` model.
- [ ] Implement `highlights` model.
- [ ] Implement `notes` model.
- [ ] Implement `collections` and `collection_items` models.
- [x] Implement `reading_states` model.
- [x] Implement `model_providers` model.

## P0 Provider System

- [x] Implement provider registry domain layer.
- [x] Implement provider CRUD API.
- [x] Implement encrypted key storage strategy.
- [x] Implement provider connection test endpoint.
- [x] Add built-in preset definitions for at least Doubao and OpenAI-compatible providers.
- [x] Implement separate model selection for summarization, embedding, and transcription.
- [x] Add desktop-side provider configuration editing for Doubao/OpenAI-compatible experiments.

Provider system note:
The API now stores provider API keys through a server-side Fernet protection helper derived from `ONERADAR_API_SECRET_KEY`, returns only `api_key_configured` to clients, and exposes a provider registry runtime resolver that maps summarization, embedding, and transcription capabilities to their separate configured models. The desktop settings page can edit the active Doubao/OpenAI-compatible provider BaseURL, API key, chat endpoint, optional transcription endpoint, and enabled state for local model experiments.

## P0 Article Ingestion

- [x] Implement URL normalization and deduplication.
- [x] Implement HTML fetch pipeline with SSRF protections.
- [x] Integrate primary article extractor.
- [x] Integrate fallback article extractor.
- [ ] Implement extraction quality scoring.
- [x] Persist raw HTML and parsed readable document.
- [ ] Build keyword/full-text search indexing for article content.
- [x] Expose article import API.

Article ingestion note:
The current backend now supports normalized manual URL import, duplicate detection, Inbox insertion, background task creation, worker-driven article completion, persistence into `content_snapshots` plus `content_parsed_documents`, API-side import URL blocking for obvious unsafe targets, and worker-side SSRF-aware fetch validation. HTML fetching now supports Trafilatura-first extraction with Readability fallback plus plain-text fallback, while still preserving SSRF-aware fetch validation. Extraction quality and downstream reader features are still not yet production-hardened.

## P0 Bilibili Ingestion

Bilibili ingestion note:
The current preferred evaluation order is `BBDown` and `Bilibili All In One` for Bilibili-specific metadata/subtitle flows, with `yt-dlp` reserved as the generic fallback. `Bilibili All In One` should be treated as a technical template candidate until its auth and credential-handling model is explicitly approved for OneRadar.
The current spike now supports Bilibili URL normalization, metadata retrieval, read-only video preview before item creation, subtitle catalog lookup, metadata-only reader fallback when subtitles are not publicly accessible, QR-code login for Bilibili Cookie acquisition, timestamp-preserving transcript persistence into the `transcripts` table, and a subtitle-miss fallback that tries a Bilibili-specific BBDown audio path, then a direct anonymous `x/player/playurl` DASH-audio path for public videos, then `yt-dlp`, before sending extracted audio through a transcription adapter. Cookie-assisted subtitle retrieval is wired end to end through the saved QR login state instead of a manual Cookie-entry UI. The ASR path currently uses the configured transcription provider and stores `asr` transcripts without leaking provider API keys into task results. Bilibili cookies are passed to media tools through temporary files/configs and are removed after each extraction attempt. `bilidown` is now tracked as the QR-login product reference, while BBDown and yt-dlp remain media retrieval references.
Optional multimodal visual enhancement is now modeled as a non-blocking model setting in the desktop settings surface. When enabled, the worker keeps subtitle/ASR as the canonical transcript, tries direct sampled-video-clip analysis first, falls back to sampled frames when needed, and stores visual model output as a `visual_context` summary without exposing provider keys.

- [x] Evaluate `BBDown` integration path.
- [x] Evaluate `yt-dlp` fallback path.
- [x] Implement Bilibili link normalization.
- [x] Implement metadata retrieval for Bilibili items.
- [x] Add Bilibili video preview before creating the item.
- [x] Implement subtitle-first retrieval path.
- [x] Implement audio extraction fallback path.
- [x] Implement transcription adapter interface.
- [x] Preserve segment timestamps in stored transcript format.
- [x] Expose Bilibili import through the same item import flow.
- [x] Add Bilibili cookie configuration surface for authenticated subtitle retrieval experiments.
- [x] Add Bilibili QR-code login flow for acquiring Cookie values.
- [x] Add desktop-side Chromium cookie import helper for Bilibili.
- [x] Add optional multimodal visual enhancement after subtitle/ASR transcript generation.

## P0 Podcast Ingestion

Podcast ingestion note:
Podcast support is now a scoped RSS exception for V1. Subscriptions discover new episodes only; they never automatically download audio or trigger model processing. Audio download starts only when a specific episode is added to Inbox / later reading, and imported podcast episodes use stable episode identities for dedupe. The desktop podcast page now supports opening a single podcast source from search or subscriptions, previewing that source's RSS episodes with a back action, and importing individual episodes from that detail view.

- [x] Add Apple iTunes Search API based podcast search endpoint.
- [x] Add server-side podcast subscription list.
- [x] Add subscribed episode feed aggregation from RSS enclosures.
- [x] Add explicit podcast episode import into Inbox / later reading.
- [x] Dedupe imported podcast episodes by stable feed/GUID identity.
- [x] Add worker pipeline that persists imported episode audio.
- [ ] Add production asset serving for persisted podcast audio.
- [x] Add podcast ASR and AI summary generation after audio download.
- [ ] Add manual re-summarize and re-transcribe controls for podcast episodes.

## P0 Reader Experience

- [x] Build desktop server connection screen (single-user, no login).
- [x] Build inbox/library list page.
- [x] Build item detail page for article content.
- [x] Build item detail page for transcript content.
- [x] Build podcast subscription and episode discovery page.
- [x] Build podcast reader audio-player surface.
- [ ] Build summary/outline panel.
- [x] Build raw-source jump-out action.
- [x] Build timestamp jump behavior for video-derived items.
- [x] Build reading state persistence.
- [ ] Build typography and layout settings.

Current note:
Desktop now uses a Chinese-first shell with `订阅源 / 稍后阅读 / 知识库 / 播客 / Bilibili` as the primary navigation and a top-right settings entry. Feed is reserved for external information streams, Inbox is the read-later buffer, Library is the formal stored collection, 播客 is the podcast subscription and episode discovery surface, and Bilibili is the dedicated video import/auth workbench. The current desktop build supports server bootstrap, unified link import into Inbox, Inbox quick-add for article/Bilibili URLs, duplicate-import UID feedback, Bilibili cookie saving, folder creation, moving items between Inbox and folders, Library preview, article detail reading, transcript detail reading, raw-source jump-out, reading progress persistence, and theme modes. Article detail now enters an immersive reader shell that removes the sidebar and global topbar so long-form reading gets the full viewport, while metadata stays in a narrower secondary rail. Reader scroll progress now syncs back to the backend and list pages surface in-progress items so users can resume from where they left off. Video transcript timestamps are now clickable reader actions that jump to the matching segment, highlight the current location, and sync that position back into reading state. Reader content uses parallel 原文 and AI tabs so summaries do not appear as a separate block inside the source reading flow.
Podcast reader content treats the audio player as the primary source surface, shows RSS episode description as `节目简介` only for podcast episodes, keeps transcript rows collapsed behind a compact expand action with timestamp jumps, and reserves the AI tab for model-generated summaries rather than source metadata. The reader now defaults to the AI tab before 原文, and AI summaries render common Markdown structure for section labels, lists, emphasis, and inline code without showing raw Markdown heading syntax. Manual summary regeneration uses long-form audio/video prompts that prioritize timestamped transcript text, include source descriptions only as supporting context, choose natural story paragraphs for casual chat/travel/story podcasts, and use conclusion/evidence/action structure for industry or knowledge podcasts.

## P0 Annotation And Organization

- [x] Implement highlight creation.
- [x] Implement note creation and editing.
- [x] Implement tag assignment.
- [x] Implement collection creation.
- [x] Implement collection membership management.
- [x] Expose annotation APIs.
- [x] Render existing highlights and notes in the reader.

Annotation note:
The backend now has first-class `highlights` and `notes` tables plus API endpoints for creating/listing highlights, creating/updating/deleting notes, and returning annotations in item detail responses. The desktop reader can create a highlight from selected text, save a note as standalone or bound to a selected/highlighted quote, display existing annotations, and delete notes.

Organization note:
The backend now has first-class `tags`, `content_item_tags`, `collections`, and `collection_items` tables. Item detail responses return persisted tags and collection memberships, item lists can filter by `tag` and `collection_id`, and the desktop reader can edit comma-separated tags, create专题, join/leave专题, and filter the Library by tag or专题.

## P0 Search

- [x] Implement item list search by keyword.
- [ ] Implement full-text result snippets.
- [ ] Implement tag filter.
- [ ] Implement collection filter.
- [ ] Implement source-type filter.

## P0 Deployment And Operations

- [x] Write Docker Compose for API, worker, Postgres, and Redis.
- [ ] Define persistent volume layout.
- [x] Add example `.env` template.
- [ ] Document local development startup.
- [ ] Document production deployment assumptions.

## P0 Testing

- [ ] Add backend unit test baseline.
- [x] Add parser/integration test baseline.
- [ ] Add Playwright test setup.
- [ ] Add E2E for article import.
- [ ] Add E2E for Bilibili import.
- [ ] Add E2E for reader detail page.
- [ ] Add E2E for search/filter flow.
- [ ] Add E2E for highlight/note flow.
- [ ] Add E2E for provider management flow.
HTTP contract coverage now exists for GET /api/feeds/preview, POST /api/items/import, POST /api/items/bilibili/preview, single-user workspace bootstrap, and the absence of public login/logout routes, including fallback-store dedup behavior, but broader parser/E2E coverage is still pending.

---

## P1 Product Depth

- [ ] Add failed-task retry UI.
- [ ] Add import status timeline.
- [ ] Add archive/favorite states.
- [ ] Add import-time note field.
- [ ] Add cover image handling where available.
- [ ] Add reading time estimate.
- [x] Add manual AI summary generation task from the reader AI tab.
- [ ] Add broader manual reprocess controls.

## P1 AI Quality

- [ ] Add one-line summary generation.
- [ ] Add short summary generation.
- [ ] Add structured outline generation.
- [ ] Add quote/evidence binding from summary sections back to source text.
- [ ] Add per-provider model fallback rules.

## P1 Security Hardening

- [ ] Restrict outbound fetch targets more tightly.
- [ ] Isolate media-processing worker runtime.
- [ ] Audit secret handling in logs and errors.
- [ ] Add provider credential rotation support.

## P1 Mobile Readiness

- [ ] Review desktop UI for responsive breakpoints.
- [ ] Separate shell-specific code from reusable UI modules.
- [ ] Document mobile/PWA adaptation constraints.

---

## P2 Later Enhancements

- [ ] Add semantic search.
- [ ] Add PDF ingestion and reading.
- [ ] Add local file import.
- [ ] Add RSS support.
RSS remains out of formal V1 scope. The current spike only adds a read-only GET /api/feeds/preview path plus desktop Feed-page preview and one-click article import against a public RSS source.
The desktop Feed page now treats saved RSS URLs as a database-backed multi-source discovery list: it can aggregate already loaded source previews, persist loaded feed item lists and read markers through the API until the source is removed, auto-refresh saved sources from the API process on a configurable timer, record refresh failures without dropping the previous cache, filter by 今天 / 近 7 天 / 全部 and 未读 / 全部 / 已读, and only creates a content item when the user explicitly adds an entry to 稍后阅读. Feed entries and article previews now surface whether the normalized/source URL already exists in saved items, showing 已加入/已保存 instead of a repeat-save action. Clicking an RSS entry marks that feed entry as read through the API and opens a transient clean reader preview through GET /api/feeds/article-preview; this preview does not create content items or enqueue AI parsing by itself, keeps a short local preview cache, and now has a 重新获取 action that clears the current preview cache before refetching. Saving a preview persists title/source metadata/cleaned text immediately and queues AI summary generation; the reader AI tab now shows AI 生成中, failed-task details, and a retry entry. HN-style RSS summaries with explicit Article URL / Comments URL are handled by a narrow URL extraction helper so reading opens the article URL when present without changing ordinary RSS behavior. This remains a read-only preview/discovery surface until a formal server-side subscription model is promoted into scope.
- [ ] Add browser extension capture.
- [ ] Add mobile packaging strategy.
- [ ] Add recommendation or related-item ranking.
- [ ] Add multi-user support.

---

## Notes

Current completed work:

- PRD rewritten into reader-first V1 scope.
- Reference and engineering-context documents created.
- Architecture, database, and API design docs created.
- Initial repo scaffold created for API, worker, desktop, packages, and infra.
- API now has schema/service baselines for single-user bootstrap, items, providers, and tasks.
- API now has SQLAlchemy/Alembic database baseline for users, content_items, processing_tasks, model_providers, artifact tables, folders, reading states, and integration settings.
- Worker completion now persists raw snapshots, parsed documents, and transcripts into first-class tables, and item APIs aggregate detail/list responses from those artifacts before falling back to `raw_meta`.
- Desktop now has API client and basic state wiring for health/bootstrap/providers/items.
- Desktop dev mode now supports same-origin /api calls through a configurable Vite proxy target, while build/preview can still pin a backend via VITE_ONERADAR_DEFAULT_API_URL.
- API contract tests now cover eeds preview parsing and items import fallback/dedup behavior.
- Relevant Codex skills installed: `frontend-skill`, `playwright`, `security-best-practices`, `transcribe`.

Next recommended execution order:

1. Add podcast production asset serving plus ASR / AI summary continuation after audio persistence.
2. Add summary generation and persistence for `one_line`, `short`, and `outline`.
3. Build PostgreSQL full-text indexing, result snippets, and tag/collection/source filters.
4. Add root-level local development scripts plus formatting, linting, type-check, and Playwright E2E setup.


