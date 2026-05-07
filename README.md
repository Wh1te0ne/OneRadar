# OneRadar

OneRadar is a self-hosted, reader-first knowledge library for manually saved articles, videos, podcasts, and RSS discoveries.

It is designed for people who want a private reading workspace rather than another public feed. You paste a link, OneRadar turns it into durable source material, and the system keeps the original content, readable text, transcripts, summaries, reading state, and organization metadata together.

## What It Does

- Saves manually submitted article links into an Inbox.
- Extracts readable article text with source-specific fallbacks, including WeChat Official Account articles.
- Handles Bilibili video links with metadata, audio retrieval, ASR-first transcription, and optional visual context.
- Lets you subscribe to podcast RSS feeds for discovery, then explicitly import episodes you want to keep.
- Maintains RSS source caches and generates a Chinese daily news brief from cached entries.
- Stores content in a server-owned library with folders, reading progress, raw source snapshots, parsed documents, transcripts, and AI summaries.
- Supports configurable model providers instead of hard-coding one LLM vendor.
- Runs as a Docker Compose server stack with a desktop/web reading UI.

## Product Boundaries

OneRadar V1 is intentionally narrow:

- Manual input first, not automated web crawling.
- Single-user and private by default.
- Chinese-first desktop/web UI.
- Server plus Windows desktop first.
- Self-hosted deployment through Docker.
- RSS and podcasts are discovery surfaces; they do not automatically import everything into the library.
- Browser extensions, public sharing, recommendation feeds, and mobile clients are outside the current scope.

## Architecture

```text
Desktop/Web UI
  -> FastAPI API
      -> PostgreSQL
      -> Redis
      -> storage artifacts
      -> worker queue
          -> article extraction
          -> Bilibili media/transcription
          -> podcast import
          -> RSS refresh and daily brief generation
          -> model-provider adapters
```

Main components:

- `apps/api`: FastAPI backend, database models, API routes, provider settings, item storage.
- `apps/worker`: Python ingestion and processing worker.
- `apps/desktop`: Tauri + React desktop/web client.
- `infra/docker`: Docker Compose files for local and production-style deployment.
- `infra/scripts`: local development bootstrap scripts.
- `docs`: product, architecture, API, database, deployment, and implementation notes.

## Local Development

Use the bundled PowerShell script so the API, worker, and desktop UI share the same local database:

```powershell
rtk pwsh -File infra/scripts/dev.ps1
```

The script starts:

- API at `http://127.0.0.1:8000/api`
- desktop dev server at `http://127.0.0.1:5173`
- worker against the same local database used by the API

Running only the API is not enough for imports. Article, Bilibili, podcast, RSS, and AI tasks are processed by the worker, so imported items can remain pending until the worker is running.

## Docker

The production-style stack is defined in `infra/docker/docker-compose.prod.yml` and uses GHCR images by default:

```bash
docker compose --env-file .env pull
docker compose --env-file .env up -d
```

Persistent data should live in host-mounted directories, not inside disposable containers. See `docs/deployment_v1.md` for the current deployment model.

## Configuration

Start from `.env.example` and provide deployment-specific secrets in ignored local files or server-side `.env` files.

Do not commit:

- API secret keys
- provider API keys
- Bilibili cookies
- SSH credentials
- Docker registry tokens
- production `.env` files

## Documentation

Before changing product scope or architecture, read these in order:

1. `docs/prd_v1_desktop_reader.md`
2. `docs/codebase_requirements.md`
3. `docs/implementation_todo.md`
4. `docs/ui_direction_v1.md`
5. `docs/reference_landscape.md`
6. `docs/deployment_v1.md`

If a change affects product scope, architecture, deployment, or sequencing, update the relevant document in the same change.

## Current Status

OneRadar is an active V1 implementation. The core server, worker, desktop UI, Docker deployment path, RSS daily brief surface, Bilibili ingestion flow, provider configuration, and reader views are already in place, but search, annotation depth, packaging polish, and production hardening are still evolving.

## License

OneRadar is licensed under the GNU Affero General Public License v3.0 only. See `LICENSE`.
