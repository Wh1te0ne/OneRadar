# Infra Scripts

Operational scripts live here.

## Local Development

Run the full local stack from the repository root:

```powershell
rtk pwsh -File infra/scripts/dev.ps1
```

`dev.ps1` starts the API, worker, and desktop dev server with a shared local sqlite database at `apps/api/oneradar.db`.
This matters because `POST /api/items/import` only creates a pending processing task; the worker must be running to fetch article HTML, extract readable text, process Bilibili/podcast items, and generate AI summaries.

Optional switches:

- `-NoDesktop`: start API and worker only.
- `-NoWorker`: start API and desktop only.
- `-DryRunWorker`: keep the worker in deterministic dry-run mode.
- `-ApiPort 8001` / `-DesktopPort 5174`: override local ports.

## Worktree Bootstrap

Git worktrees do not include ignored local state such as `.venv-api`, `apps/desktop/node_modules`, `.env.production.local`, `infra/private/`, or sqlite runtime data.

After creating a new worktree, run this from that worktree root:

```powershell
rtk pwsh -File infra/scripts/bootstrap-worktree.ps1
```

This creates `.venv-api`, installs API and worker Python dependencies, and runs `npm install` for `apps/desktop`.

Production credentials and private access files are not copied by default. If a worktree explicitly needs the ignored local deployment files from the main checkout, use:

```powershell
rtk pwsh -File infra/scripts/bootstrap-worktree.ps1 -CopyPrivate -SourceRepoRoot E:\OneRadar
```

Do not commit copied private files; they stay ignored by `.gitignore`.
