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

### 2026-06 Scope Reset

- [x] Reframe OneRadar as RSS/news radar plus transient link-analysis API instead of a built-in reading library.
- [x] Remove Library/knowledge-base, Inbox/read-later, reader, notes, highlights, folders, and collections from the primary desktop UI.
- [x] Keep RSS entries as source-level news entries with direct original-link opening, not reader-preview items.
- [x] Remove read/unread state from RSS UI.
- [x] Add a desktop link-analysis workbench for no-save URL analysis.
- [x] Add a desktop API/MCP surface for integration tokens and capability visibility.
- [x] Keep model/provider configuration as a first-class settings surface.
- [ ] Add production-grade transient adapters for YouTube, Douyin, Xiaohongshu, and WeChat links beyond generic webpage extraction or metadata preview.

Current adapter note:
Douyin and Xiaohongshu transient URL analysis now uses the open-source MIT `parsehub` Python package. The API extracts visible platform text and media metadata without downloading or saving media, and can receive optional server-side Cookie/proxy settings through environment variables. YouTube remains pending.

- [x] Replace single-user no-login mode with lightweight private-deployment login/register flow.
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
- [x] Add root-level scripts for local development.
- [ ] Add formatting, linting, and type-check commands.

## P0 Backend Foundations

- [x] Implement health check and authenticated user bootstrap path.
- [x] Implement username/email + password login and registration.
- [x] Scope API requests to the authenticated user.
- [x] Add user-created integration tokens for MCP/service access.
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
The API now stores provider API keys through a server-side Fernet protection helper derived from `ONERADAR_API_SECRET_KEY`, returns only `api_key_configured` to clients, and exposes a provider registry runtime resolver that maps summarization, embedding, and transcription capabilities to their separate configured models. The desktop settings page supports Doubao, DeepSeek, OpenAI-compatible, and custom LLM providers plus Doubao ASR. Provider records are user-created, must be complete before saving, and only one provider per capability can be current/enabled at a time. Provider config records model input capabilities as text, image, audio, and video flags for later media-routing decisions, without asking users to maintain unclear vendor limits such as maximum file size, maximum duration, or long-audio/video support. LLM providers can also store a unified per-provider thinking-mode preference in provider config. DeepSeek and Doubao both use `thinking.type`; DeepSeek additionally sends `reasoning_effort=medium` when thinking is enabled, while Doubao does not use the LAS-only `thinking_type`.

## P0 Article Ingestion

- [x] Implement URL normalization and deduplication.
- [x] Implement HTML fetch pipeline with SSRF protections.
- [x] Integrate primary article extractor.
- [x] Integrate fallback article extractor.
- [x] Implement extraction quality scoring.
- [x] Persist raw HTML and parsed readable document.
- [ ] Build keyword/full-text search indexing for article content.
- [x] Expose article import API.

Article ingestion note:
The current backend now supports normalized manual URL import, duplicate detection, Inbox insertion, background task creation, worker-driven article completion, persistence into `content_snapshots` plus `content_parsed_documents`, API-side import URL blocking for obvious unsafe targets, and worker-side SSRF-aware fetch validation. HTML fetching now supports Trafilatura-first extraction with Readability fallback plus plain-text fallback, while still preserving SSRF-aware fetch validation. Live article fetching is now formal-use oriented: when a live fetch is blocked or unavailable, the worker fails/retries the item instead of persisting demo article content. `mp.weixin.qq.com` links now use a dedicated lightweight WeChat Official Account parser before the generic HTML extraction path, so verification/error pages fail clearly instead of being summarized as article content. Parsed article output also preserves detected body heading levels, list blocks, and quote blocks in `structured_blocks` for reader rendering. Extraction quality scoring now penalizes residual HTML/script-like text, short fragments, noisy recommendation/footer sections, and source HTML/body length mismatch before choosing among extraction candidates. RSS article preview applies the same residual-tag and tail-noise cleanup so preview and saved-reader content do not diverge on common dirty pages.

## P0 Bilibili Ingestion

Bilibili ingestion note:
The current preferred evaluation order is `BBDown` and `Bilibili All In One` for Bilibili-specific metadata/subtitle flows, with `yt-dlp` reserved as the generic fallback. `Bilibili All In One` should be treated as a technical template candidate until its auth and credential-handling model is explicitly approved for OneRadar.
The current spike now supports Bilibili URL normalization, metadata retrieval, read-only video preview before item creation, subtitle catalog lookup, QR-code login for Bilibili Cookie acquisition, timestamp-preserving subtitle transcript persistence into task metadata, and an ASR fallback path that tries a Bilibili-specific BBDown audio path, then a direct anonymous `x/player/playurl` DASH-audio path for public videos, then `yt-dlp`, before sending extracted audio through a transcription adapter. Subtitles are fetched whenever available so reader timestamp jumps and later model prompts have timeline context; ASR remains available when subtitles are missing, when the current text-only path needs a fuller transcript, or when multimodal analysis fails. Cookie-assisted metadata/media retrieval is wired end to end through the saved QR login state instead of a manual Cookie-entry UI. The ASR path currently uses the configured transcription provider and stores `asr` transcripts without leaking provider API keys into task results. Bilibili cookies are passed to media tools through temporary files/configs and are removed after each extraction attempt. `bilidown` is now tracked as the QR-login product reference, while BBDown and yt-dlp remain media retrieval references.
Multimodal video/audio handling is now driven by each configured LLM provider's input capability flags instead of a separate Bilibili visual-enhancement toggle. For video-capable models, the worker first tries sampled video clip analysis with subtitle context, then falls back to sampled frames if image input is supported, and finally ASR if the multimodal path fails or no readable transcript exists. For audio-capable models, the worker can send extracted audio plus subtitle context before falling back to ASR. Text-only models use the subtitle/ASR text path. Subtitle text is always included in later summary prompts when available, even if ASR produced a similar transcript, to reduce content loss.

- [x] Evaluate `BBDown` integration path.
- [x] Evaluate `yt-dlp` fallback path.
- [x] Implement Bilibili link normalization.
- [x] Implement metadata retrieval for Bilibili items.
- [x] Add Bilibili video preview before creating the item.
- [x] Implement capability-driven Bilibili transcript and multimodal retrieval path.
- [x] Implement audio extraction fallback path.
- [x] Implement transcription adapter interface.
- [x] Preserve segment timestamps in stored transcript format.
- [x] Expose Bilibili import through the same item import flow.
- [x] Add Bilibili cookie configuration surface for authenticated subtitle retrieval experiments.
- [x] Add Bilibili QR-code login flow for acquiring Cookie values.
- [x] Add desktop-side Chromium cookie import helper for Bilibili.
- [x] Add provider-capability-driven multimodal video/audio analysis with subtitle context and ASR fallback.

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
- [x] Add responsive mobile web shell over the same API/data model.

Current note:
Desktop now uses a Chinese-first shell with `每日新闻 / 信息源 / 链接分析 / 调用接口 / 设置` as the primary navigation. 每日新闻 is the RSS-backed daily brief, 信息源 is the RSS source and cached-entry operations surface, 链接分析 is a temporary URL workbench that returns original text/visible platform text, summary, metadata, and JSON without saving a reading item, 调用接口 exposes MCP and analysis API endpoints plus integration tokens, and 设置 keeps provider/model configuration as a first-class workflow.
The primary desktop UI no longer exposes 稍后阅读, Library, internal reader routes, reader progress, read/unread RSS state, notes, highlights, folders, collections, podcast discovery, or Bilibili import as product navigation. Legacy backend routes and old components may remain temporarily for data compatibility, but they are not primary product surfaces.
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

Local development now has `infra/scripts/dev.ps1`, which starts the API, worker, and desktop dev server together against the same sqlite database. This prevents manual imports from staying indefinitely in `待处理` because only the API was running.

## P0 Search

- [x] Implement item list search by keyword.
- [ ] Implement full-text result snippets.
- [ ] Implement tag filter.
- [ ] Implement collection filter.
- [ ] Implement source-type filter.

## P0 Deployment And Operations

- [x] Write Docker Compose for API, worker, Postgres, and Redis.
- [x] Define persistent volume layout.
- [x] Add example `.env` template.
- [x] Document local development startup.
- [x] Document production deployment assumptions.

Deployment note:
`docs/deployment_v1.md` now records the intended split between local development/testing, private GitHub source control, and Docker Compose based production on the remote server. Tracked docs intentionally omit live passwords and direct future agents to ignored local files for machine-specific access notes. The production Compose stack now includes explicit bind-mounted data directories for Postgres, Redis, and application artifacts, plus an Nginx-served web frontend container on port 8080.

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
- [x] Add desktop update check indicator and settings-page manual version check.
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
- [x] Document mobile/PWA adaptation constraints.
- [x] Add native Android client source referencing the existing mobile web UI.

Android client note:
The Android source lives in `apps/android` and implements a native client over the existing OneRadar API. The local workspace now has a repo-local Android toolchain path documented in `apps/android/README.md`, can build a debug APK, and has been validated in a local Android emulator. The current Android client covers login, daily news, read-later/library/feed lists, knowledge-base folder create/filter/rename/delete management, reader detail with AI/source tabs, source jump-out, mark-read, move-to-folder, summary-task trigger, and native model provider configuration while preserving the existing API/data model.

---

## P2 Later Enhancements

- [ ] Add semantic search.
- [ ] Add PDF ingestion and reading.
- [ ] Add local file import.
- [x] Add RSS support.
RSS is now a controlled source-management and daily-brief surface, not a broad automatic ingestion path and not a read-later queue. The current implementation keeps manual source subscription, database-backed feed state, refresh status, source/date filters, and direct original-link opening. It does not expose read/unread state or save-to-Inbox behavior in the primary RSS UI.
The desktop Feed page treats saved RSS URLs as a database-backed multi-source discovery list: it loads source and entry state from the API, persists fetched feed entries until the source is removed, auto-refreshes saved sources from the API process on a user-editable minute/hour timer, records refresh failures without dropping previous cached entries, filters by 今天 / 近 7 天 / 全部 and source, and opens RSS entries directly at their original links. Minute refresh intervals are aligned to clock-hour boundaries instead of save time. Subscribed source refresh uses `limit=0` by default so the parser stores every entry present in the feed response, and database upsert keeps older cached entries even when the source later exposes only its newest items. New or changed non-Chinese feed entries are translated during the refresh/cache path and persisted with Chinese title/summary fields; the UI displays titles as `中文版本 ---> 原始标题` and summaries as Chinese when available. HN-style RSS summaries with explicit Article URL / Comments URL are handled by a narrow URL extraction helper so opening uses the article URL when present without changing ordinary RSS behavior.
The 每日新闻 page is the first formal RSS homepage: it reads cached RSS entries from the 24 hours before the actual generation time, calls the configured summarization/chat model to translate and summarize them into a fixed daily-brief structure, persists one report per user per date, and opens section entries at their original source URLs. The generated daily brief is AI-first: headline/lead must prefer AI news when available, the first section must be AI, AI coverage should be heavier than other topics, and game news is last. The API schedules default generation at 10:00 Asia/Shanghai and the desktop UI supports previous/next date browsing, date picking, missing-date generation, confirmed regeneration that overwrites the existing report for that day, and a read-only share link using an opaque user share key plus date so different users can share different reports for the same date. The share page renders only the daily brief content without source-management or regeneration controls, and its title links open the original RSS URLs. It intentionally avoids automatic item import and independent RSS display areas.
OneRadar now also exposes a built-in `/api/mcp` JSON-RPC endpoint for Hermes Agent. The initial MCP tools list RSS source state and return raw structured entries for a requested time window, defaulting to the previous 24 hours. This MCP path is intentionally hosted inside the existing API container, not a separate Docker service, so PostgreSQL remains the single news-source state owner and Hermes remains responsible for AI grouping and delivery.
- [ ] Add browser extension capture.
- [x] Add mobile packaging strategy.
- [ ] Add recommendation or related-item ranking.
- [x] Add lightweight private-deployment multi-user support.
  This is intentionally first-stage account isolation, not SaaS/team functionality. Existing local/NAS data is preserved under the `whiteone` bootstrap account, while new users receive separate provider settings, RSS state, folders, collections, content, annotations, and reports.

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


