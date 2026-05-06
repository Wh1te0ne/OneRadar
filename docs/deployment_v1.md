# OneRadar Deployment V1

## Purpose

This document records the intended development, GitHub, and production deployment model for the web/server side of OneRadar.

It must not contain live passwords, API keys, provider keys, cookies, or private SSH material. Machine-specific secrets belong only in ignored local files such as `.env.production.local` or files under `infra/private/`.

## Environment Roles

OneRadar should use three distinct roles:

- Local development and testing: the Windows workstation is the primary place to edit code, run tests, and validate desktop/web behavior.
- GitHub source control: GitHub stores the private repository and is the canonical code history, review, and release coordination point.
- Production server: the remote server runs the web/server stack through Docker Compose and owns persistent web data.

Current private repository:

- `https://github.com/Wh1te0ne/OneRadar`

Current production server identity:

- Host: `101.96.202.98`
- SSH user: `root`

The production SSH password is intentionally omitted from this tracked document.

## Scope Boundary

This deployment model applies to the web/server side only:

- API service
- worker service
- PostgreSQL
- Redis
- persisted content artifacts and generated media/text outputs

Future Windows desktop and Android clients should connect to the server API, but their packaging and release channels are separate deployment concerns.

## Production Deployment Shape

Production should deploy from the GitHub repository onto the target server with Docker Compose.

Baseline services:

- `api`
- `worker`
- `postgres`
- `redis`

Optional later services:

- reverse proxy for TLS and stable external routing
- backup sidecar or scheduled backup job
- object storage if local disk persistence becomes limiting

## Persistent Data

Production must persist at least:

- PostgreSQL data volume
- raw HTML snapshots and parsed article artifacts
- podcast audio artifacts imported by explicit user action
- Bilibili audio/transcript intermediates that are intentionally retained
- generated transcripts and summaries
- server-side provider and integration settings

The Docker Compose baseline uses explicit host-directory bind mounts through `ONERADAR_DATA_ROOT`, not anonymous container storage. For production, use the repo-local server path:

```text
/root/Project/OneRadar/data
/root/Project/OneRadar/backups
```

The current layout is:

```text
/root/Project/OneRadar
  .env
  infra/docker/docker-compose.yml
  data/
    postgres/
    redis/
    storage/
    backups/
```

Production `.env` should set:

```text
ONERADAR_DATA_ROOT=/root/Project/OneRadar/data
ONERADAR_STORAGE_ROOT=/app/data/storage
```

## Secret Handling

Rules:

- Never commit `.env`, `.env*.local`, `infra/private/`, SSH keys, provider API keys, Bilibili cookies, or production passwords.
- Keep production provider keys and source-site credentials server-side only.
- Do not echo raw secrets in deployment logs, issue comments, PR descriptions, or task results.
- Prefer SSH key authentication over a root password when the server is ready for hardening.
- Rotate the current root password after SSH-key access is configured.

## Update Flow

The intended update flow is:

1. Develop and test locally.
2. Commit and push to the private GitHub repository.
3. SSH to the production server.
4. Pull the target branch or release tag.
5. Rebuild and restart Docker Compose services.
6. Run a health check against the API.

Initial command shape, to be refined once the server path and compose wrapper are finalized:

```powershell
ssh root@101.96.202.98
cd /root/Project/OneRadar
git pull
docker compose -f infra/docker/docker-compose.yml up -d --build
docker compose -f infra/docker/docker-compose.yml ps
```

## Open Decisions

- Final production checkout path on the server.
- Whether to expose API directly or behind a reverse proxy.
- TLS certificate strategy.
- Backup schedule and restore drill.
- Whether production deploys from `main`, tags, or a dedicated release branch.
- Whether GitHub Actions should later SSH into the server, or whether deployments remain manually pulled from the server.
