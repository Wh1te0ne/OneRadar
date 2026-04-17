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

## Operating Rules

- Read the required docs before implementing anything substantial.
- Start from `docs/implementation_todo.md` and work top-down by priority unless the user redirects.
- When a checkbox-worthy task is completed, update `docs/implementation_todo.md` in the same change.
- When architecture decisions become concrete, create or update `docs/architecture_v1.md`, `docs/database_v1.md`, and `docs/api_v1.md`.
- Keep documentation synchronized with code changes.
- Prefer small, composable adapters over large framework-heavy abstractions.

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
