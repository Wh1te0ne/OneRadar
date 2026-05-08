# AGENTS.md

## Purpose

This repository is for building OneRadar.

The primary failure mode for future work is context drift. Before making product or architecture changes, read the documents below in order.

## Required Reading Order

1. docs/prd_v1_desktop_reader.md
2. docs/codebase_requirements.md
3. docs/implementation_todo.md
4. docs/ui_direction_v1.md
5. docs/reference_landscape.md

If a task changes product scope, architecture, or sequencing, update the relevant document in the same task.

## Product Boundaries

Keep these constraints stable unless explicitly changed in the docs:

- V1 is reader-first, not a general web capture platform.
- Input is manual link submission only.
- Manual input includes article links and Bilibili video links.
- V1 does not include RSS, browser extension capture, or automated harvesting.
- V1 is server plus Windows desktop first.
- Server deployment must support Docker.
- Provider configuration is a first-class feature.
- V1 is single-user and should avoid user-facing login/account flows.
- New imports enter Inbox first and can be moved into folders.
- The desktop UI is Chinese-first in V1 and should support light/dark/system theme modes.
- Use the item UUID as the stable user-visible UID unless the docs explicitly change that decision.

## Engineering Direction

Preferred stack:

- Backend: Python + FastAPI + PostgreSQL + Redis + worker queue
- Desktop: Tauri + React
- Search: keyword/full-text first
- Article extraction: Readability plus Trafilatura style approach
- Video ingestion: subtitle-first, ASR-second

Do not hard-code the system around a single model vendor.

## Production NAS

Before answering or changing deployment details, check `docs/deployment_v1.md` and `infra/docker/docker-compose.prod.yml`; do not rely on memory.

Current production NAS reference:

- Host: `192.168.100.55`
- SSH user: `wh1teone`
- Runtime path: `/vol1/1000/Workspace/OneRadar`
- Data root: `/vol1/1000/Workspace/OneRadar/data`
- Backups path: `/vol1/1000/Workspace/OneRadar/backups`
- Browser entrypoint: `http://192.168.100.55:8081`
- Health check: `http://192.168.100.55:8081/api/health`

Secret lookup rule:

- Do not store live passwords, provider keys, cookies, or private SSH material in `AGENTS.md` or tracked docs.
- When deployment access or credentials are needed, look in ignored local storage first: `.env.production.local` and files under `infra/private/`.
- Never print raw secrets in task output, logs, commits, PRs, or issue comments.

Deployment order is mandatory:

1. Develop and test in the current local Windows environment first.
2. Commit and push the verified change to GitHub.
3. Let GitHub Actions publish GHCR images.
4. SSH to the NAS and update by `docker compose pull` / `docker compose up -d`.

Normal NAS updates are image-based from GHCR, not source-copy based. Do not copy local source files or locally built images to the NAS as a shortcut:

```powershell
ssh wh1teone@192.168.100.55
cd /vol1/1000/Workspace/OneRadar
docker compose --env-file .env pull
docker compose --env-file .env up -d
docker compose --env-file .env ps
curl http://192.168.100.55:8081/api/health
```

## Operating Rules

- Read the required docs before implementing anything substantial.
- Start from `docs/implementation_todo.md` and work top-down by priority unless the user redirects.
- When a checkbox-worthy task is completed, update `docs/implementation_todo.md` in the same change.
- When architecture decisions become concrete, create or update `docs/architecture_v1.md`, `docs/database_v1.md`, and `docs/api_v1.md`.
- Keep documentation synchronized with code changes.
- Prefer small, composable adapters over large framework-heavy abstractions.
- Git worktrees do not carry ignored local state. After creating a worktree, run `rtk pwsh -File infra/scripts/bootstrap-worktree.ps1` in that worktree before local development or tests. Use `-CopyPrivate -SourceRepoRoot E:\OneRadar` only when that worktree explicitly needs ignored deployment access files.

## External References

Before reinventing major product or pipeline decisions, review:

- docs/reference_landscape.md

For frontend and interaction work, follow:

- docs/ui_direction_v1.md

Use these docs to identify reusable open-source components, reference products, licensing constraints, and the approved UI baseline.
## Skills Guidance

Installed skills currently relevant to this repo:

- `frontend-skill`
- `playwright`
- `security-best-practices`
- `transcribe`

Use them when the task clearly matches.

Remember:

- `transcribe` is a development aid for validating ASR workflow and timestamp output.
- It is not itself the product architecture.

## Shell Rule

Per local environment rules, shell commands should be prefixed with `rtk`.

When a shell command needs PowerShell semantics, prefer PowerShell 7 via `rtk pwsh` or `rtk powershell`.

Use Windows PowerShell only when a command specifically depends on it or an approved prefix already requires it.

If direct `rtk` shell wrapping hangs on a read or scripting command, prefer `rtk proxy ...` with an explicit shell executable instead of retrying the same form.

## Definition Of Done

A feature is not done unless all of the following are true:

- Code or docs for the task are actually written.
- Relevant checklist items are updated.
- Any changed scope or architecture is reflected in the docs.
- Basic verification has been run when applicable.
