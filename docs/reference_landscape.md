# OneRadar Reference Landscape

## Purpose

This document records the external products, libraries, and Codex skills that are worth reusing as references while building OneRadar.

It is not a list of things to blindly adopt. It exists to reduce repeated research and keep architectural decisions stable.

## How To Use This Document

For each new feature, check this document before designing from scratch.

Decision rules:

- Reuse product ideas, not entire product complexity.
- Reuse libraries for narrow infrastructure jobs where licenses and operating assumptions fit.
- Avoid copying AGPL product code into OneRadar unless the licensing decision is explicit.
- Prefer small, well-bounded dependencies over adopting a full product codebase.

## Product References

### 1. Omnivore

Repo: [omnivore-app/omnivore](https://github.com/omnivore-app/omnivore)

Why it matters:

- Strong reference for reader-first information architecture.
- Good model for highlights, notes, search, and saved reading position.
- Useful benchmark for article detail page UX and keyboard-friendly reading flows.

What to reuse as inspiration:

- Reading detail page structure.
- Highlight and note interaction patterns.
- Saved progress and read-state concepts.

What not to copy directly:

- Full product scope, browser extension ecosystem, and social/productivity extras.
- AGPL product code without explicit licensing intent.

### 2. Linkwarden

Repo: [linkwarden/linkwarden](https://github.com/linkwarden/linkwarden)

Why it matters:

- Very relevant for the overlap between bookmarking, readable snapshots, annotations, and preservation.
- Strong reference for archive-oriented product thinking.

What to reuse as inspiration:

- Item organization and archive mindset.
- Reader view plus annotation coexistence.
- Long-term preservation thinking for links that may rot.

What not to copy directly:

- Team collaboration and broader archive features that are outside V1.

### 3. Karakeep

Repo: [karakeep-app/karakeep](https://github.com/karakeep-app/karakeep)

Why it matters:

- Useful reference for self-hosted collection products that mix links, AI metadata, and search.
- Good signal for what users now expect from bookmark/read-later tooling.

What to reuse as inspiration:

- Inbox/list organization patterns.
- Auto-tagging and enrichment ideas for later phases.
- Cross-platform product framing.

What not to copy directly:

- Huge scope including mobile apps, RSS, OCR, and broad capture inputs.

### 4. wallabag

Repo: [wallabag/wallabag](https://github.com/wallabag/wallabag)

Why it matters:

- Mature self-hosted read-later reference.
- Useful for simpler article-saving and reader-mode patterns.

What to reuse as inspiration:

- Minimal read-later flows.
- Article extraction mental model.
- Server-first product packaging.

### 5. Shiori

Repo: [go-shiori/shiori](https://github.com/go-shiori/shiori)

Why it matters:

- Good reference for a lighter-weight, more pragmatic bookmark/archive product.
- Helps keep OneRadar from drifting into unnecessary complexity.

What to reuse as inspiration:

- Small-scope MVP thinking.
- Offline/archive-first bookmark behavior.

## Reusable Infrastructure Components

### 1. Web Article Extraction

#### Mozilla Readability

Repo: [mozilla/readability](https://github.com/mozilla/readability)

Use for:

- Reader-mode style extraction.
- Clean main-content parsing from article pages.

Recommended role in OneRadar:

- One of the first-pass article parsers.
- Best paired with fallback extraction instead of used alone.

#### Trafilatura

Repo: [adbar/trafilatura](https://github.com/adbar/trafilatura)

Use for:

- Robust text and metadata extraction.
- Structured extraction pipelines with metadata retention.

Recommended role in OneRadar:

- Main server-side article extraction candidate.
- Fallback or co-primary parser with Readability.

Suggested strategy:

- Try parser A.
- Score the output.
- Retry with parser B on poor-quality extraction.

### 2. Bilibili / Video Retrieval

#### yt-dlp

Repo: [yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp)

Use for:

- Generic media metadata retrieval and audio/video extraction.
- Broad support and active maintenance.

Recommended role in OneRadar:

- Baseline fetcher for media URLs and downloadable streams.
- General fallback when a platform-specific tool is not enough.

#### BBDown

Repo: [nilaoda/BBDown](https://github.com/nilaoda/BBDown)

Use for:

- Bilibili-specific metadata, audio, subtitle, and stream handling.
- Cases where Bilibili-specific behavior matters more than generality.

Recommended role in OneRadar:

- Primary Bilibili ingestion candidate.
- Especially useful when subtitles and platform details matter.

Important note:

- Use must remain compliant with applicable law and content rights.
- Do not design the product around mass downloading or redistribution.

#### ClawHub Skill: Bilibili All In One

Reference: [clawhub.ai/wscats/bilibili-all-in-one](https://clawhub.ai/wscats/bilibili-all-in-one)

Snapshot checked:

- 2026-04-14
- version `1.0.21`
- license `MIT-0`

Why it matters:

- It is a compact end-to-end reference for Bilibili-specific workflows in one place instead of separate tools.
- The published capability surface includes hot monitoring, video downloading, playback, subtitle downloading, and publishing, which makes it useful for understanding how a Bilibili-focused skill bundles auth and media operations.
- For OneRadar, the relevant value is implementation reference for metadata, subtitle retrieval, and download fallback behavior rather than product scope inspiration.

What to reuse as inspiration:

- Bilibili credential input patterns for explicitly opt-in authenticated actions.
- Subtitle-first and media-download fallback handling ideas.
- Lightweight Python packaging shape for a narrowly scoped external ingestion helper.

What not to copy directly:

- Hot monitoring, watcher, and publish flows are outside OneRadar V1 scope.
- Any credential persistence pattern that writes live browser session cookies into the repo or shared workspace.

Operational cautions:

- The ClawHub page says optional credentials are `SESSDATA`, `bili_jct`, `buvid3`, and `BILIBILI_PERSIST`.
- The page also says persistence is opt-in and may save credentials to `.credentials.json` in the project root with `0600` permissions.
- Treat these values as full-session cookies. Do not store real personal Bilibili cookies in the OneRadar repo, sample env files, or shared development notes.

Recommended role in OneRadar:

- Keep this as a future technical reference when implementing Bilibili download/subtitle support.
- Prefer evaluating it alongside BBDown and yt-dlp if the initial Bilibili ingestion path needs a more integrated auth-aware helper.
- Do not treat it as an approved product dependency until its code, runtime domains, and credential handling are reviewed in the context of OneRadar's security model.

### 3. Transcription

#### faster-whisper

Repo: [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper)

Use for:

- Self-hosted ASR.
- Lower-cost transcription where local or server inference is preferable.

Recommended role in OneRadar:

- Strong candidate for self-hosted transcription provider.
- Useful when user-managed servers should avoid per-call API cost.

#### WhisperX

Repo: [m-bain/whisperX](https://github.com/m-bain/whisperX)

Use for:

- Better timestamp quality.
- Alignment-sensitive scenarios.
- Speaker-aware or word-level timestamp improvements.

Recommended role in OneRadar:

- Optional higher-fidelity transcription path for timestamp-heavy use cases.
- Worth evaluating when Bilibili clip jumping accuracy matters.

## Recommended Product Strategy From These References

For V1, OneRadar should combine ideas like this:

- Product shape from Omnivore and Linkwarden.
- Scope discipline from Shiori.
- Article parsing from Readability plus Trafilatura.
- Bilibili ingestion from BBDown or Bilibili All In One, with yt-dlp as a generic fallback.
- Transcription abstraction that can target subtitles first, then ASR via provider adapters.

## Licensing Guidance

Before adopting code from any reference project, check the license again.

High-level guidance:

- Omnivore: AGPL-3.0
- Linkwarden: AGPL-3.0
- Karakeep: AGPL-3.0
- wallabag: open source, but still review exact subcomponent licenses before reuse
- Shiori: MIT
- Readability: open source JS library, suitable as a dependency
- Trafilatura: Apache-2.0
- yt-dlp: Unlicense
- BBDown: MIT
- faster-whisper: MIT
- WhisperX: BSD-2-Clause

Rule:

- Product ideas are safe to study.
- Direct code reuse must be checked deliberately.

## Codex Skill Guidance

Installed skills currently relevant to this repo:

- `transcribe`: Use for validating ASR workflow and timestamp output during development, not as a product dependency by itself.
- `frontend-skill`: Use when implementing reader UI, list flows, and desktop-shell-facing frontend work.
- `playwright`: Use for end-to-end verification of import, reading, search, and annotation flows.
- `security-best-practices`: Use when implementing URL ingestion, provider secrets, SSRF controls, and Docker/network boundaries.
- `doc`: Low priority for this repo because the main project docs are Markdown, not DOCX.

Skills that may be worth adding later:

- `pdf` if PDF becomes part of near-term scope.
- A project-specific custom skill for Bilibili ingestion and provider management.

## What To Avoid

Avoid these common mistakes:

- Building the whole product around automatic capture inputs too early.
- Treating transcription as the product instead of one pipeline stage.
- Pulling in an entire read-later product codebase because it feels faster.
- Letting AGPL reference code leak into the repo without an explicit decision.
- Designing provider support around one hard-coded model vendor.


