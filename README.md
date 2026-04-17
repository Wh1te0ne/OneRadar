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

## Next Steps

- complete app skeletons under `apps/`
- wire local development commands
- implement health/auth/import/provider baselines
- add first ingestion pipeline for articles
