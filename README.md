# OneRadar

OneRadar is a reader-first personal knowledge library for manually submitted links.

V1 scope:

- manual link input only
- article URLs and Bilibili video URLs
- server-first architecture
- Windows desktop client first
- Docker deployment for the server
- provider registry for summarization, embedding, and transcription

## Repo Layout

```text
E:\OneRadar
  AGENTS.md
  README.md
  .env.example
  apps/
    api/
    worker/
    desktop/
  packages/
    shared/
    provider-adapters/
    content-adapters/
    prompts/
  infra/
    docker/
    scripts/
  docs/
```

## Source Of Truth

Read these before changing code or architecture:

1. `docs/prd_v1_desktop_reader.md`
2. `docs/codebase_requirements.md`
3. `docs/implementation_todo.md`
4. `docs/reference_landscape.md`

## Initial Bootstrap Goal

The current repo is being bootstrapped toward:

- a FastAPI API app
- a Python worker app
- a Tauri + React desktop app
- a Docker Compose development stack

## Local Development

Use the bundled PowerShell script so the API, worker, and desktop UI share the same local database:

```powershell
rtk pwsh -File infra/scripts/dev.ps1
```

The script starts:

- API at `http://127.0.0.1:8000/api`
- desktop dev server at `http://127.0.0.1:5173`
- worker against `apps/api/oneradar.db`

Running only the API is not enough for imports. Article, Bilibili, podcast, and AI tasks are processed by the worker, so imported items may stay in `待处理` until the worker is running.

## Next Steps

- complete app skeletons under `apps/`
- implement health/auth/import/provider baselines
- add first ingestion pipeline for articles
