# OneRadar Deployment V1

## Purpose

This document records the intended development, GitHub, and production deployment model for the web/server side of OneRadar.

It must not contain live passwords, API keys, provider keys, cookies, or private SSH material. Machine-specific secrets belong only in ignored local files such as `.env.production.local` or files under `infra/private/`.

## Environment Roles

OneRadar should use three distinct roles:

- Local development and testing: the Windows workstation is the primary place to edit code, run tests, and validate desktop/web behavior.
- GitHub source control: GitHub stores the private repository and is the canonical code history, review, and release coordination point.
- Production NAS: the NAS runs the web/server stack through Docker Compose and owns persistent web data.

Current private repository:

- `https://github.com/Wh1te0ne/OneRadar`

Current production NAS identity:

- Host: `192.168.100.55`
- SSH user: `wh1teone`
- Project path: `/vol1/1000/Workspace/OneRadar`

The production SSH password is intentionally omitted from this tracked document.

## Scope Boundary

This deployment model applies to the web/server side only:

- web frontend
- API service
- worker service
- PostgreSQL
- Redis
- persisted content artifacts and generated media/text outputs

Future Windows desktop and Android clients should connect to the server API, but their packaging and release channels are separate deployment concerns.

## Production Deployment Shape

Production should run prebuilt GHCR images on the target NAS with Docker Compose.

The NAS runtime directory should not be a source checkout. It should contain only:

- `docker-compose.yml`
- `.env`
- `data/`

Normal updates should be:

```bash
docker compose --env-file .env pull
docker compose --env-file .env up -d
```

Baseline services:

- `web`
- `api`
- `worker`
- `postgres`
- `redis`

Only `web` and `api` should publish host ports in the baseline production stack. PostgreSQL and Redis remain reachable only on the Docker internal network and persist through host bind mounts. The web host port is controlled by `ONERADAR_WEB_PORT`.

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

The Docker Compose baseline uses explicit host-directory bind mounts through `ONERADAR_DATA_ROOT`, not anonymous container storage. For production, use the repo-local NAS path:

```text
/vol1/1000/Workspace/OneRadar/data
/vol1/1000/Workspace/OneRadar/backups
```

The current layout is:

```text
/vol1/1000/Workspace/OneRadar
  .env
  docker-compose.yml
  data/
    postgres/
    redis/
    storage/
    backups/
```

Production `.env` should set:

```text
ONERADAR_DATA_ROOT=/vol1/1000/Workspace/OneRadar/data
ONERADAR_STORAGE_ROOT=/app/data/storage
ONERADAR_API_PORT=18000
ONERADAR_WEB_PORT=8081
ONERADAR_PUBLIC_API_URL=http://192.168.100.55:18000
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
3. GitHub Actions builds and publishes GHCR images.
4. SSH to the production NAS.
5. Run `docker compose --env-file .env pull`.
6. Run `docker compose --env-file .env up -d`.
7. Run a health check against the API.

Initial command shape, to be refined once the server path and compose wrapper are finalized:

```powershell
ssh wh1teone@192.168.100.55
cd /vol1/1000/Workspace/OneRadar
docker compose --env-file .env pull
docker compose --env-file .env up -d
docker compose --env-file .env ps
```

## Open Decisions

- Whether to expose API directly or behind a reverse proxy.
- TLS certificate strategy.
- Backup schedule and restore drill.
- Whether production deploys from `main`, tags, or a dedicated release branch.
- Whether GitHub Actions should later SSH into the NAS, or whether deployments remain manually pulled from the NAS.
