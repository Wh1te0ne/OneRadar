# OneRadar Codebase Requirements

## Purpose

This document defines the minimum repo shape, engineering constraints, and implementation rules for OneRadar.

If a future coding task is unclear, this file should be treated as the working contract for the repo.

## Primary Product Constraints

The repo must preserve these V1 boundaries:

- V1 is a reader-first personal knowledge library.
- Input is manual link submission only.
- Manual input supports article links, Bilibili video links, and podcast episodes explicitly added from subscribed podcast feeds.
- V1 does not include browser extension capture or broad automated harvesting. RSS is a scoped, user-managed discovery surface: saved sources may be refreshed, viewed, used to generate one persisted daily news brief per date, and exposed as raw time-windowed news data to Hermes Agent through the built-in MCP endpoint. RSS entries are not imported into the reading library unless the user explicitly saves them. Podcast RSS remains the scoped podcast exception for subscriptions and episode discovery.
- V1 is server plus Windows desktop client first.
- The server must support Docker deployment.
- AI provider configuration must be user-manageable.
- V1 formal mode supports lightweight private-deployment accounts with username/email plus password login and registration. It is not a SaaS/team system.
- New imports land in Inbox first and can then be moved into folders.
- The desktop UI is Chinese-first in V1.
- The desktop UI must support light, dark, and system theme modes.

## Core Architectural Direction

### Backend

Preferred stack:

- Python
- FastAPI
- PostgreSQL
- Redis
- Worker queue

Required backend responsibilities:

- Link normalization and deduplication.
- Article fetching and readable-text extraction.
- Bilibili metadata retrieval and audio-to-text transcription. Platform subtitles may be inspected as metadata, but they are not the default canonical transcript source.
- Podcast search/subscription, RSS episode discovery, and explicit podcast episode import.
- Capability-driven Bilibili multimodal enhancement after subtitle retrieval, without replacing the readable transcript or timeline source.
- Podcast audio must not download automatically on subscription; it downloads only after the user adds an episode to Inbox / later reading.
- Storage of raw materials and readable documents.
- Provider registry and model selection.
- Authentication and per-user data isolation for provider settings, RSS state, folders, collections, reading items, annotations, and generated reports.
- Search, highlights, notes, folders/collections, and reading state.

### Desktop Client

Preferred stack:

- Tauri
- React

Required desktop responsibilities:

- Connect to configured server and authenticate with username/email plus password.
- Submit links.
- Display Inbox, folders, and library lists.
- Render article text and transcript text in a Reader-like layout.
- Support annotations, labels, folders, collections, and search.
- Expose provider, theme, account, and connection settings.
- Support Bilibili QR-code login as the primary credential flow for authenticated subtitle retrieval.

### Cross-Platform Principle

Design the UI as web-first but not web-only.

Implications:

- Reuse business logic and page structure where possible.
- Do not overfit interaction design to desktop-only assumptions.
- Keep native-shell integrations isolated from core UI logic.

## Required Repo Structure

Target structure for the initial codebase:

```text
E:\OneRadar
  AGENTS.md
  docs/
    prd_v1_desktop_reader.md
    reference_landscape.md
    codebase_requirements.md
    implementation_todo.md
    architecture_v1.md
    api_v1.md
    database_v1.md
    deployment_v1.md
  apps/
    desktop/
    api/
    worker/
  packages/
    shared/
    provider-adapters/
    content-adapters/
    prompts/
  infra/
    docker/
    scripts/
```

If the actual structure changes later, update this document and `AGENTS.md` in the same change.

## Required Documentation Discipline

These documents are mandatory context anchors:

- `docs/prd_v1_desktop_reader.md`: source of truth for product scope.
- `docs/codebase_requirements.md`: source of truth for engineering constraints.
- `docs/implementation_todo.md`: source of truth for active priorities and completion status.
- `docs/reference_landscape.md`: source of truth for external references and reusable components.
- `docs/deployment_v1.md`: source of truth for local/GitHub/production deployment assumptions.

Rule:

- Any change that materially alters scope, architecture, or sequencing must update the relevant doc in the same task.

## Provider System Requirements

Provider support must be designed as a first-class subsystem.

Required capabilities:

- Presets for common providers such as Doubao and DeepSeek without creating default provider records.
- Ability to add custom providers.
- Support for OpenAI-compatible endpoints where possible.
- Separate model selection for chat/summarization, embedding, and transcription.
- Encrypted or otherwise protected API key storage on the server.
- One enabled/current provider per capability, with LLM and ASR selection kept separate.
- Connection testing.

Required abstraction direction:

- `provider registry`
- `chat/summarization adapter`
- `embedding adapter`
- `transcription adapter`
- `video visual-understanding adapter`

Do not hard-code the product around one model vendor.

## Ingestion Pipeline Requirements

### Article Pipeline

Minimum required stages:

1. Normalize URL.
2. Fetch HTML.
3. Extract metadata.
4. Extract readable body.
5. Score output quality.
6. Store raw and cleaned forms.
7. Build search index.
8. Optionally summarize.

### Bilibili Pipeline

Minimum required stages:

1. Normalize URL.
2. Fetch metadata.
3. Try subtitle retrieval first.
4. If subtitles fail, fetch audio or media stream.
5. Transcribe with timestamps.
6. Build readable transcript view.
7. Summarize and outline.
8. Preserve jump-back timestamps.

Rule:

- Subtitle-first, ASR-second.
- Summary must never be the only stored representation.
- QR-code login is the preferred Bilibili authentication path; manual Cookie entry and desktop browser Cookie scraping are not part of the primary V1 UI.
- Multimodal video analysis is an optional model setting and must not replace timestamped subtitles or ASR output.
- When enabled, video visual analysis should prefer direct sampled-video input for providers that support it, with sampled-frame analysis as the fallback path.

### Podcast Pipeline

Minimum required stages:

1. Search podcasts through Apple iTunes Search API.
2. Store user-managed podcast RSS subscriptions.
3. Preview subscribed RSS feeds for episode metadata.
4. Create a unified `content_item` only when the user explicitly adds an episode to Inbox / later reading.
5. Dedupe episode imports by feed URL plus GUID, with enclosure URL as fallback.
6. Download and persist episode audio only for imported episodes.
7. Transcribe and summarize imported episodes as derived outputs.
8. Delete the persisted audio artifact when the imported podcast episode item is deleted.

Rule:

- Subscribing to a podcast never downloads audio and never triggers model processing by itself.
- Podcast audio is a reprocessing source artifact; transcript text is supporting material, not the primary reader surface.
- Podcast reader surfaces should prioritize the audio player, summaries, metadata, and notes.

## Search Requirements

V1 search priorities:

- Title search.
- Full-text search.
- Tag filtering.
- Collection filtering.

V1 non-priority:

- Semantic retrieval.
- Recommendation systems.

## Annotation Requirements

The data model and UI must assume these are core, not optional polish:

- Highlights.
- Notes.
- Tags.
- Collections.
- Reading state.

If a feature competes with these for time, these win.

## Security Requirements

Minimum security requirements:

- SSRF-aware URL ingestion.
- Server-side secret storage only.
- Restricted media download and processing environment.
- Auth on file and asset access.
- Log redaction for keys, cookies, and secrets.
- Separation between provider configuration and user-facing logs.

## Testing Requirements

Expected testing pyramid for early phases:

- Unit tests for parser and adapter logic.
- Integration tests for provider registry and ingestion pipeline stages.
- Playwright end-to-end coverage for core user flows.

Core E2E flows that must eventually exist:

- Import article link.
- Import Bilibili link.
- Open library item.
- Search and filter items.
- Create highlight and note.
- Update provider settings.

## Delivery Rules

When implementing features:

- Start from `docs/implementation_todo.md`.
- Update checkboxes when a task is meaningfully complete.
- If scope changes, update the PRD and this file before or alongside code.
- Keep documentation in sync with the repo, not as a later cleanup step.

## Open Decisions To Resolve Later

These are intentionally unresolved for now:

- Final queue technology.
- Exact DB migration tooling.
- Exact transcription provider defaults.
- Whether mobile ships as PWA first or a separate native shell.

Until decided, avoid premature deep coupling.

## Identity And UID Requirements

- Each imported item must receive a stable UID bound to that record.
- The UID is cleared only when the item itself is deleted.
- Duplicate imports must return an explicit already-exists response and the existing UID.
- It is acceptable for the primary content item UUID to serve as this UID in V1.

## Single-User Constraint

- Keep internal user ownership structures if they simplify persistence, but do not build a user-facing account system in V1.
- Desktop should open into the workspace, not a login product flow.
