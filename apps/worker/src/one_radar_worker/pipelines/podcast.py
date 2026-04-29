from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .common import PipelineContext, PipelineRunResult, PipelineStepResult
from ..transcription import (
    TranscriptionError,
    is_transcription_configured,
    select_transcription_adapter,
)


@dataclass(slots=True)
class PodcastAudioDownload:
    ok: bool
    audio_path: str | None = None
    content_type: str | None = None
    content_length: int | None = None
    final_url: str | None = None
    error_message: str | None = None


def _guess_extension(url: str, content_type: str | None) -> str:
    suffix = Path(urlsplit(url).path).suffix.lower()
    if suffix in {".m4a", ".mp3", ".wav", ".aac", ".flac", ".ogg", ".opus", ".mp4"}:
        return suffix
    normalized_type = (content_type or "").casefold()
    if "mpeg" in normalized_type:
        return ".mp3"
    if "mp4" in normalized_type or "m4a" in normalized_type:
        return ".m4a"
    if "wav" in normalized_type:
        return ".wav"
    if "ogg" in normalized_type:
        return ".ogg"
    return ".audio"


def _media_root(payload: dict[str, object]) -> Path:
    configured = str(payload.get("media_library_root") or "").strip()
    if configured:
        return Path(configured)
    return Path(os.getenv("ONERADAR_MEDIA_LIBRARY_ROOT", "data/media"))


class PodcastPipeline:
    timeout_seconds = 900

    def _download_audio(self, context: PipelineContext) -> PodcastAudioDownload:
        enclosure_url = str(context.payload.get("enclosure_url") or "").strip()
        if not enclosure_url:
            return PodcastAudioDownload(ok=False, error_message="podcast enclosure url is required")

        output_dir = _media_root(context.payload) / "podcasts" / str(context.item_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        request = Request(
            enclosure_url,
            headers={
                "Accept": "audio/*,*/*;q=0.1",
                "User-Agent": "OneRadarWorker/0.1",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                content_type = response.headers.get("Content-Type")
                content_length_text = response.headers.get("Content-Length")
                extension = _guess_extension(getattr(response, "url", enclosure_url), content_type)
                audio_path = output_dir / f"source{extension}"
                with audio_path.open("wb") as file:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        file.write(chunk)
                try:
                    content_length = int(content_length_text) if content_length_text else audio_path.stat().st_size
                except ValueError:
                    content_length = audio_path.stat().st_size
                return PodcastAudioDownload(
                    ok=True,
                    audio_path=str(audio_path),
                    content_type=content_type,
                    content_length=content_length,
                    final_url=getattr(response, "url", enclosure_url),
                )
        except Exception as exc:  # noqa: BLE001
            return PodcastAudioDownload(ok=False, error_message=str(exc))

    def run(self, context: PipelineContext) -> PipelineRunResult:
        steps: list[PipelineStepResult] = []
        download = self._download_audio(context)
        steps.append(
            PipelineStepResult(
                step_name="download_podcast_audio",
                ok=download.ok,
                message=download.error_message or "podcast audio downloaded",
                data={
                    "audio_path": download.audio_path,
                    "content_type": download.content_type,
                    "content_length": download.content_length,
                    "final_url": download.final_url,
                },
            )
        )
        if not download.ok or not download.audio_path:
            return PipelineRunResult(ok=False, steps=steps, data={"error_message": download.error_message})

        transcript_payload = None
        provider_config = context.payload.get("transcription_provider")
        if isinstance(provider_config, dict) and provider_config:
            try:
                if not is_transcription_configured(provider_config):
                    raise TranscriptionError("transcription provider is not configured")
                transcript_payload = select_transcription_adapter(provider_config).transcribe(
                    audio_path=download.audio_path,
                    mime_type=download.content_type,
                    provider_config=provider_config,
                    language=str(context.payload.get("language") or "") or None,
                ).to_dict()
                steps.append(
                    PipelineStepResult(
                        step_name="transcribe_podcast_audio",
                        ok=True,
                        message="podcast audio transcribed",
                        data={
                            "provider_name": transcript_payload.get("provider_name"),
                            "model_name": transcript_payload.get("model_name"),
                        },
                    )
                )
            except TranscriptionError as exc:
                steps.append(
                    PipelineStepResult(
                        step_name="transcribe_podcast_audio",
                        ok=False,
                        message=str(exc),
                    )
                )

        title = str(context.payload.get("title") or "未命名播客单集")
        podcast_title = str(context.payload.get("podcast_title") or "")
        summary = str(context.payload.get("summary") or "").strip()
        source_url = str(context.payload.get("episode_link") or context.source_url)
        content_hash = sha256(f"{context.payload.get('feed_url')}:{context.payload.get('guid')}:{context.payload.get('enclosure_url')}".encode("utf-8")).hexdigest()
        podcast_meta = {
            "feed_url": context.payload.get("feed_url"),
            "podcast_title": podcast_title,
            "guid": context.payload.get("guid"),
            "episode_link": context.payload.get("episode_link"),
            "enclosure_url": context.payload.get("enclosure_url"),
            "enclosure_type": context.payload.get("enclosure_type") or download.content_type,
            "enclosure_length": context.payload.get("enclosure_length") or download.content_length,
            "image_url": context.payload.get("image_url"),
            "audio_storage_path": download.audio_path,
        }
        data = {
            "source_url": source_url,
            "normalized_url": context.payload.get("normalized_url"),
            "host": urlsplit(source_url).hostname,
            "fetch": {
                "mode": "podcast_enclosure",
                "status_code": 200,
                "content_type": download.content_type,
                "final_url": download.final_url,
                "error_message": None,
            },
            "persistable": {
                "content_item": {
                    "title": title,
                    "subtitle": podcast_title or None,
                    "author_name": context.payload.get("author"),
                    "cover_url": context.payload.get("image_url"),
                    "duration_seconds": context.payload.get("duration_seconds"),
                    "published_at": context.payload.get("published_at"),
                    "content_hash": content_hash,
                    "raw_meta": {
                        "podcast": podcast_meta,
                        "audio_source_kind": "podcast_enclosure",
                    },
                },
                "raw_snapshot": {
                    "snapshot_type": "podcast_audio",
                    "storage_path": download.audio_path,
                    "status_code": 200,
                    "content_hash": content_hash,
                    "content_type": download.content_type,
                    "final_url": download.final_url,
                    "source_headers": {},
                },
                "parsed_document": {
                    "parser_name": "podcast_metadata",
                    "parser_version": "v1",
                    "title": title,
                    "excerpt": summary or None,
                    "byline": context.payload.get("author"),
                    "language": None,
                    "plain_text": summary,
                    "structured_blocks": [{"type": "summary", "text": summary}] if summary else [],
                    "quality_score": None,
                },
                "transcript": transcript_payload,
                "summaries": [
                    {
                        "summary_type": "short",
                        "content": summary,
                        "model_name": None,
                        "version": 1,
                        "evidence": [],
                    }
                ]
                if summary
                else [],
            },
        }
        return PipelineRunResult(ok=True, steps=steps, data=data)
