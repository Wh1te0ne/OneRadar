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

### 3. Podcast Search And RSS

#### Apple iTunes Search API

Docs: [iTunes Search API](https://performance-partners.apple.com/resources/documentation/itunes-store-web-service-search-api/)

Use for:

- Podcast search without a user-provided API key.
- Resolving podcast search results to RSS `feedUrl` values when Apple exposes them.

Recommended role in OneRadar:

- MVP podcast discovery provider.
- Use server-side proxy endpoints so the desktop UI does not depend directly on Apple response shape.

Limitations:

- Apple search coverage and `feedUrl` availability are not guaranteed for every podcast.
- Keep manual RSS input or future Podcast Index integration available as fallback paths.

#### Podcast RSS Enclosures

Use for:

- Discovering episode metadata.
- Locating episode audio through RSS `<enclosure>` URLs.

Recommended role in OneRadar:

- Store user-managed podcast RSS subscriptions.
- Never download audio just because a feed is subscribed.
- Download and persist audio only after a user explicitly adds an episode to Inbox / later reading.

#### bilidown

Repo: [iuroc/bilidown](https://github.com/iuroc/bilidown)

License:

- Apache-2.0

Why it matters:

- It is a user-facing Bilibili downloader with an explicit QR-code login flow, which makes it more useful as a product interaction reference than command-line fetchers.
- It demonstrates a practical shape for letting a desktop user authorize Bilibili access without manually copying browser cookies.
- Its supported URL surface includes single videos, series, collections, favorites, and watch-later style inputs, which is useful when deciding how far OneRadar should or should not expand beyond manual single-link ingestion.

What to reuse as inspiration:

- Application-level QR-code login UX: generate QR code, show scan status, poll login state, save cookies after confirmation.
- Clear login-state feedback instead of asking the user to infer whether a pasted cookie is valid.
- Treating authenticated Bilibili access as an explicit user action, not background browser session scraping.

What not to copy directly:

- Downloader-first scope, batch download management, tray-centric task behavior, and broad collection/favorite import flows are outside OneRadar V1.
- Go plus SQLite application architecture does not match the preferred OneRadar FastAPI plus Tauri stack.
- Direct code reuse still requires targeted review even though the license is permissive.

Operational cautions:

- QR-code login returns full-session credentials such as `SESSDATA` and `bili_jct`, and may also return refresh-token data depending on the endpoint behavior.
- Store successful QR-login credentials only in the server-side integration settings layer, keep API responses masked, and redact logs.
- QR-code URLs and keys are short-lived login material; do not persist them beyond the active login attempt.

Recommended role in OneRadar:

- Use as the main product reference for Bilibili QR-code authorization.
- Keep BBDown and yt-dlp as media/subtitle/audio fetch references; keep bilidown as the login and authenticated-user-flow reference.
- Prefer QR-code login as the recommended Cookie acquisition path in the desktop UI, with manual paste and local Chromium Cookie import retained as fallbacks.

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
- Bilibili login UX from bilidown-style QR-code authorization, while keeping credential storage inside OneRadar's server-side integration settings.
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


