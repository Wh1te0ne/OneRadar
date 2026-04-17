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

- [ ] Remove user-facing login/account flow from desktop and backend UX.
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
- [ ] Decide provider abstraction interfaces.
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

- [ ] Implement provider registry domain layer.
- [x] Implement provider CRUD API.
- [ ] Implement encrypted key storage strategy.
- [x] Implement provider connection test endpoint.
- [x] Add built-in preset definitions for at least Doubao and OpenAI-compatible providers.
- [ ] Implement separate model selection for summarization, embedding, and transcription.

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
The current spike now supports Bilibili URL normalization, metadata retrieval, subtitle catalog lookup, metadata-only reader fallback when subtitles are not publicly accessible, desktop-side Chromium cookie import for authenticated subtitle attempts, and timestamp-preserving transcript persistence into the `transcripts` table. Cookie-assisted subtitle retrieval is now wired end to end, while audio-to-ASR fallback is still unfinished.

- [ ] Evaluate `BBDown` integration path.
- [ ] Evaluate `yt-dlp` fallback path.
- [x] Implement Bilibili link normalization.
- [x] Implement metadata retrieval for Bilibili items.
- [x] Implement subtitle-first retrieval path.
- [ ] Implement audio extraction fallback path.
- [ ] Implement transcription adapter interface.
- [x] Preserve segment timestamps in stored transcript format.
- [x] Expose Bilibili import through the same item import flow.
- [x] Add Bilibili cookie configuration surface for authenticated subtitle retrieval experiments.
- [x] Add desktop-side Chromium cookie import helper for Bilibili.

## P0 Reader Experience

- [x] Build desktop server connection screen (single-user, no login).
- [x] Build inbox/library list page.
- [x] Build item detail page for article content.
- [ ] Build item detail page for transcript content.
- [ ] Build summary/outline panel.
- [x] Build raw-source jump-out action.
- [ ] Build timestamp jump behavior for video-derived items.
- [ ] Build reading state persistence.
- [ ] Build typography and layout settings.

Current note:
Desktop now uses a Chinese-first shell with `Feed / Inbox / Library / 导入` as the primary navigation and a top-right settings entry. Feed is reserved for external information streams, Inbox is the read-later buffer, Library is the formal stored collection, and 导入 is the dedicated workbench for manual link submission plus Bilibili cookie configuration. The current desktop build supports server bootstrap, unified link import into Inbox, duplicate-import UID feedback, Bilibili cookie saving, folder creation, moving items between Inbox and folders, Library preview, article detail reading, raw-source jump-out, and theme modes.

## P0 Annotation And Organization

- [ ] Implement highlight creation.
- [ ] Implement note creation and editing.
- [ ] Implement tag assignment.
- [ ] Implement collection creation.
- [ ] Implement collection membership management.
- [ ] Expose annotation APIs.
- [ ] Render existing highlights and notes in the reader.

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
HTTP contract coverage now exists for GET /api/feeds/preview and POST /api/items/import, including fallback-store dedup behavior, but broader parser/E2E coverage is still pending.

---

## P1 Product Depth

- [ ] Add failed-task retry UI.
- [ ] Add import status timeline.
- [ ] Add archive/favorite states.
- [ ] Add import-time note field.
- [ ] Add cover image handling where available.
- [ ] Add reading time estimate.
- [ ] Add manual reprocess controls.

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
- API now has schema/service baselines for auth, items, providers, and tasks.
- API now has SQLAlchemy/Alembic database baseline for users, content_items, processing_tasks, model_providers, artifact tables, folders, reading states, and integration settings.
- Worker completion now persists raw snapshots, parsed documents, and transcripts into first-class tables, and item APIs aggregate detail/list responses from those artifacts before falling back to `raw_meta`.
- Desktop now has API client and basic state wiring for health/login/providers/items.
- Desktop dev mode now supports same-origin /api calls through a configurable Vite proxy target, while build/preview can still pin a backend via VITE_ONERADAR_DEFAULT_API_URL.
- API contract tests now cover eeds preview parsing and items import fallback/dedup behavior.
- Relevant Codex skills installed: `frontend-skill`, `playwright`, `security-best-practices`, `transcribe`.

Next recommended execution order:

1. Decide provider abstraction interfaces.
2. Harden article fetching and extraction with SSRF protections plus real extractor integration.
3. Finish Bilibili audio extraction and ASR fallback.
4. Add summary generation and persistence for `one_line`, `short`, and `outline`.
5. Start reader actions and annotation APIs.






