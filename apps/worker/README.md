# OneRadar Worker

This directory contains the V1 worker skeleton for OneRadar.

## Scope

The worker is responsible for async processing only. It does not expose the HTTP API and it does not run the desktop UI.

Planned job flow:

1. Receive a task from the API server or queue.
2. Resolve the task type.
3. Run the relevant pipeline stage.
4. Persist raw snapshots, parsed text, transcripts, summaries, and task state.
5. Mark the task success or failure.

## Supported V1 task types

- `fetch_meta`
- `fetch_html`
- `extract_article`
- `fetch_subtitles`
- `extract_audio`
- `transcribe_audio`
- `generate_summary`
- `build_index`
- `reprocess_item`
- `sync_provider_test`

## Pipeline overview

Article jobs:

- normalize URL
- fetch metadata and HTML
- extract readable text
- score extraction quality
- prepare a persistable payload for content items, raw snapshots, and parsed documents
- generate summary
- build search index

Bilibili jobs:

- normalize URL
- fetch metadata
- try subtitles first
- fall back to BBDown, direct Bilibili `playurl` audio, then `yt-dlp`, audio extraction and ASR through the configured transcription provider
- store timestamped transcript
- generate summary and outline
- build search index

## Article pipeline skeleton

The article worker now does more than return a stub.
It performs the following V1-friendly steps:

- normalize the input URL
- prefer provided HTML or a dry-run demo payload when running locally
- attempt a primary extraction strategy and a fallback strategy
- score extraction quality
- emit a structured persistable payload that maps cleanly to future API/database writes

The result is intentionally shaped so the API layer can later store:

- raw HTML snapshot metadata
- cleaned readable text
- structured blocks
- quality score and scoring reasons
- summary inputs

## Bilibili ASR fallback

The Bilibili pipeline is subtitle-first. If no usable subtitle transcript is available, it:

- extracts audio with a subprocess-based BBDown wrapper first
- uses a direct Bilibili `x/player/playurl` DASH-audio path before `yt-dlp` so public videos can work without browser cookies when that legacy API is available
- resolves the enabled model provider with a `transcription_model`
- submits the audio to the transcription adapter
- stores the result as an `asr` transcript with timestamped segments when the provider returns them

Provider API keys are decrypted only inside the worker process and are not copied into task results. Bilibili cookies are passed to media tools through temporary files/configs and are removed after each extraction attempt.

## Current status

This is still a skeleton, but it is now structured enough to be wired to the API server and queue later.

For local dry runs, the worker uses an embedded demo article payload so the pipeline stays deterministic without network access.
