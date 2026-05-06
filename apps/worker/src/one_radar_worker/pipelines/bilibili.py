from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import os
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from ..media_audio import AudioExtractor, BilibiliAudioExtractor
from ..media_visual import (
    BilibiliLegacyFrameExtractor,
    BilibiliLegacyVideoClipExtractor,
    OpenAICompatibleVisualUnderstandingAdapter,
    VisualFrameExtractor,
    VisualUnderstandingAdapter,
    VisualUnderstandingResult,
    VisualVideoExtractor,
)
from ..transcription import (
    TranscriptionAdapter,
    TranscriptionError,
    is_transcription_configured,
    select_transcription_adapter,
)
from .common import (
    PipelineContext,
    PipelineDocumentBlock,
    PipelineQualityScore,
    PipelineRunResult,
    PipelineStepResult,
)

BILIBILI_CANONICAL_HOST = 'www.bilibili.com'
BILIBILI_HOSTS = {
    'bilibili.com',
    'www.bilibili.com',
    'm.bilibili.com',
}
BILIBILI_SHORT_HOSTS = {
    'b23.tv',
    'bili22.cn',
    'bili23.cn',
    'bili2233.cn',
}
PREFERRED_SUBTITLE_LANGS = (
    'zh-CN',
    'zh-Hans',
    'zh-Hant',
    'ai-zh',
    'en-US',
    'en',
)
SUBTITLE_TRANSCRIPTS_ENABLED = False


@dataclass(slots=True)
class BilibiliVideoRef:
    source_url: str
    normalized_url: str
    bvid: str | None
    aid: int | None
    page: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BilibiliFetchResult:
    step_name: str
    ok: bool
    request_url: str
    response_data: dict[str, Any]
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BilibiliSubtitleTrack:
    subtitle_url: str
    language: str | None
    label: str | None
    is_ai: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BilibiliTranscriptPayload:
    transcript_type: str
    language: str | None
    full_text: str
    segments: list[dict[str, Any]]
    provider_name: str | None = None
    model_name: str | None = None
    confidence_score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BilibiliVideoMetadata:
    bvid: str | None
    aid: int | None
    cid: int | None
    page: int
    title: str
    description: str
    owner_name: str | None
    owner_id: str | None
    cover_url: str | None
    duration_seconds: int | None
    published_at: str | None
    part_title: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _build_headers(referer: str | None = None, cookie_values: dict[str, str | None] | None = None) -> dict[str, str]:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 OneRadar/0.1',
        'Accept': 'application/json,text/plain,*/*',
    }
    if referer:
        headers['Referer'] = referer

    cookie_parts: list[str] = []
    provided_map = {
        'SESSDATA': (cookie_values or {}).get('sessdata'),
        'bili_jct': (cookie_values or {}).get('bili_jct'),
        'buvid3': (cookie_values or {}).get('buvid3'),
    }
    env_map = {
        'SESSDATA': os.getenv('ONERADAR_BILIBILI_SESSDATA'),
        'bili_jct': os.getenv('ONERADAR_BILIBILI_BILI_JCT'),
        'buvid3': os.getenv('ONERADAR_BILIBILI_BUVID3'),
    }
    merged_map = {key: provided_map.get(key) or env_map.get(key) for key in env_map}
    for key, value in merged_map.items():
        if value:
            cookie_parts.append(f'{key}={value}')
    if cookie_parts:
        headers['Cookie'] = '; '.join(cookie_parts)
    return headers


def _ensure_scheme(url: str) -> str:
    candidate = url.strip()
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', candidate):
        return f'https://{candidate}'
    return candidate


def _parse_page(query: str) -> int:
    parsed = parse_qs(query)
    raw_page = parsed.get('p', ['1'])[0]
    try:
        page = int(raw_page)
    except ValueError:
        return 1
    return page if page > 0 else 1


def _canonicalize_bilibili_url(url: str) -> BilibiliVideoRef:
    ensured = _ensure_scheme(url)
    parsed = urlsplit(ensured)
    host = parsed.netloc.lower()
    page = _parse_page(parsed.query)
    path = parsed.path.rstrip('/') or '/'
    normalized_url = urlunsplit((parsed.scheme.lower() or 'https', host, path, urlencode({'p': page}) if page > 1 else '', ''))

    video_match = re.search(r'/video/(?P<id>(BV[0-9A-Za-z]+|av\d+))', path, flags=re.IGNORECASE)
    if not video_match:
        return BilibiliVideoRef(source_url=url, normalized_url=normalized_url, bvid=None, aid=None, page=page)

    raw_id = video_match.group('id')
    bvid = f"BV{raw_id[2:]}" if raw_id.upper().startswith('BV') else None
    aid = None
    if raw_id.lower().startswith('av'):
        try:
            aid = int(raw_id[2:])
        except ValueError:
            aid = None

    canonical_id = bvid or f'av{aid}' if aid is not None else raw_id
    normalized_host = BILIBILI_CANONICAL_HOST if host in BILIBILI_HOSTS else host
    normalized_path = f'/video/{canonical_id}'
    normalized_query = urlencode({'p': page}) if page > 1 else ''
    normalized_url = urlunsplit(('https', normalized_host, normalized_path, normalized_query, ''))
    return BilibiliVideoRef(source_url=url, normalized_url=normalized_url, bvid=bvid, aid=aid, page=page)


def _resolve_short_url(url: str, cookie_values: dict[str, str | None] | None = None) -> str:
    request = Request(_ensure_scheme(url), headers=_build_headers(cookie_values=cookie_values))
    with urlopen(request, timeout=10) as response:
        return getattr(response, 'url', url)


def _normalize_video_ref(raw_url: str, cookie_values: dict[str, str | None] | None = None) -> BilibiliVideoRef:
    ensured = _ensure_scheme(raw_url)
    host = urlsplit(ensured).netloc.lower()
    if host.startswith('www.'):
        host = host[4:]
    if host in BILIBILI_SHORT_HOSTS:
        resolved = _resolve_short_url(ensured, cookie_values=cookie_values)
        return _canonicalize_bilibili_url(resolved)
    return _canonicalize_bilibili_url(ensured)


def _request_json(url: str, referer: str | None = None, cookie_values: dict[str, str | None] | None = None) -> dict[str, Any]:
    request = Request(url, headers=_build_headers(referer=referer, cookie_values=cookie_values))
    with urlopen(request, timeout=15) as response:
        raw = response.read().decode('utf-8', errors='replace')
    return json.loads(raw)


def _fetch_metadata(video_ref: BilibiliVideoRef, cookie_values: dict[str, str | None] | None = None) -> BilibiliFetchResult:
    if video_ref.bvid:
        request_url = f'https://api.bilibili.com/x/web-interface/view?bvid={video_ref.bvid}'
    elif video_ref.aid is not None:
        request_url = f'https://api.bilibili.com/x/web-interface/view?aid={video_ref.aid}'
    else:
        return BilibiliFetchResult('fetch_metadata', False, video_ref.normalized_url, {}, 'unsupported bilibili url')

    try:
        payload = _request_json(request_url, referer=video_ref.normalized_url, cookie_values=cookie_values)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError) as error:
        return BilibiliFetchResult('fetch_metadata', False, request_url, {}, str(error))

    if int(payload.get('code', -1)) != 0:
        return BilibiliFetchResult(
            'fetch_metadata',
            False,
            request_url,
            payload,
            str(payload.get('message') or payload.get('msg') or 'metadata request failed'),
        )
    return BilibiliFetchResult('fetch_metadata', True, request_url, payload)


def _extract_video_metadata(video_ref: BilibiliVideoRef, metadata_payload: dict[str, Any]) -> BilibiliVideoMetadata:
    data = metadata_payload.get('data') or {}
    pages = data.get('pages') or []
    selected_page = pages[min(len(pages), max(video_ref.page, 1)) - 1] if pages else {}
    published_at = None
    pubdate = data.get('pubdate')
    if isinstance(pubdate, (int, float)):
        published_at = datetime.fromtimestamp(pubdate, tz=UTC).isoformat()

    owner = data.get('owner') or {}
    cid = selected_page.get('cid') or data.get('cid')
    aid = data.get('aid')
    if not isinstance(aid, int):
        try:
            aid = int(aid) if aid is not None else None
        except (TypeError, ValueError):
            aid = None

    return BilibiliVideoMetadata(
        bvid=data.get('bvid') or video_ref.bvid,
        aid=aid if aid is not None else video_ref.aid,
        cid=int(cid) if cid is not None else None,
        page=video_ref.page,
        title=str(data.get('title') or 'Bilibili 视频').strip(),
        description=str(data.get('desc') or '').strip(),
        owner_name=str(owner.get('name') or '').strip() or None,
        owner_id=str(owner.get('mid')) if owner.get('mid') is not None else None,
        cover_url=str(data.get('pic') or '').strip() or None,
        duration_seconds=int(data.get('duration')) if data.get('duration') is not None else None,
        published_at=published_at,
        part_title=str(selected_page.get('part') or '').strip() or None,
    )


def _fetch_subtitle_catalog(video_ref: BilibiliVideoRef, metadata: BilibiliVideoMetadata, cookie_values: dict[str, str | None] | None = None) -> BilibiliFetchResult:
    if metadata.cid is None:
        return BilibiliFetchResult('fetch_subtitles', False, video_ref.normalized_url, {}, 'missing cid for subtitle request')

    if metadata.bvid:
        request_url = f'https://api.bilibili.com/x/player/v2?cid={metadata.cid}&bvid={metadata.bvid}'
    elif metadata.aid is not None:
        request_url = f'https://api.bilibili.com/x/player/v2?cid={metadata.cid}&aid={metadata.aid}'
    else:
        return BilibiliFetchResult('fetch_subtitles', False, video_ref.normalized_url, {}, 'missing bilibili identifiers for subtitle request')

    try:
        payload = _request_json(request_url, referer=video_ref.normalized_url, cookie_values=cookie_values)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError) as error:
        return BilibiliFetchResult('fetch_subtitles', False, request_url, {}, str(error))

    if int(payload.get('code', -1)) != 0:
        return BilibiliFetchResult(
            'fetch_subtitles',
            False,
            request_url,
            payload,
            str(payload.get('message') or payload.get('msg') or 'subtitle request failed'),
        )
    return BilibiliFetchResult('fetch_subtitles', True, request_url, payload)


def _select_subtitle_track(catalog_payload: dict[str, Any]) -> BilibiliSubtitleTrack | None:
    subtitle_root = (catalog_payload.get('data') or {}).get('subtitle') or {}
    raw_tracks = subtitle_root.get('subtitles') or subtitle_root.get('list') or []
    candidates: list[BilibiliSubtitleTrack] = []
    for entry in raw_tracks:
        if not isinstance(entry, dict):
            continue
        subtitle_url = str(entry.get('subtitle_url') or entry.get('url') or '').strip()
        if not subtitle_url:
            continue
        if subtitle_url.startswith('//'):
            subtitle_url = f'https:{subtitle_url}'
        candidates.append(
            BilibiliSubtitleTrack(
                subtitle_url=subtitle_url,
                language=str(entry.get('lan') or '').strip() or None,
                label=str(entry.get('lan_doc') or entry.get('label') or '').strip() or None,
                is_ai=bool(entry.get('ai_type') or entry.get('ai_status') or entry.get('is_ai')),
            )
        )
    if not candidates:
        return None

    def rank(track: BilibiliSubtitleTrack) -> tuple[int, int]:
        try:
            priority = PREFERRED_SUBTITLE_LANGS.index(track.language or '')
        except ValueError:
            priority = len(PREFERRED_SUBTITLE_LANGS)
        return (priority, 1 if track.is_ai else 0)

    return sorted(candidates, key=rank)[0]


def _fetch_subtitle_transcript(track: BilibiliSubtitleTrack, referer: str, cookie_values: dict[str, str | None] | None = None) -> BilibiliTranscriptPayload | None:
    try:
        payload = _request_json(track.subtitle_url, referer=referer, cookie_values=cookie_values)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None

    raw_body = payload.get('body') or []
    segments: list[dict[str, Any]] = []
    texts: list[str] = []
    for entry in raw_body:
        if not isinstance(entry, dict):
            continue
        text = str(entry.get('content') or '').strip()
        if not text:
            continue
        start_ms = int(round(float(entry.get('from', 0)) * 1000))
        end_ms = int(round(float(entry.get('to', entry.get('from', 0))) * 1000))
        segments.append(
            {
                'start_ms': max(0, start_ms),
                'end_ms': max(max(0, start_ms), end_ms),
                'text': text,
                'speaker': None,
            }
        )
        texts.append(text)

    if not segments:
        return None

    return BilibiliTranscriptPayload(
        transcript_type='subtitle',
        language=track.language,
        full_text='\n'.join(texts),
        segments=segments,
    )


def _transcript_blocks(transcript: BilibiliTranscriptPayload) -> list[PipelineDocumentBlock]:
    blocks: list[PipelineDocumentBlock] = []
    for index, segment in enumerate(transcript.segments):
        blocks.append(
            PipelineDocumentBlock(
                block_type='transcript_segment',
                text=str(segment['text']),
                order=index,
                data={
                    'start_ms': int(segment['start_ms']),
                    'end_ms': int(segment['end_ms']),
                },
            )
        )
    return blocks


def _description_blocks(description: str) -> list[PipelineDocumentBlock]:
    lines = [line.strip() for line in description.splitlines() if line.strip()]
    return [PipelineDocumentBlock(block_type='paragraph', text=line, order=index) for index, line in enumerate(lines)]


def _quality_score(transcript: BilibiliTranscriptPayload | None, description: str) -> PipelineQualityScore:
    if transcript and transcript.full_text.strip():
        if transcript.transcript_type == 'asr':
            return PipelineQualityScore(value=75.0, reasons=['asr transcript available'])
        return PipelineQualityScore(value=85.0, reasons=['subtitle transcript available'])
    if description.strip():
        return PipelineQualityScore(value=40.0, reasons=['metadata description fallback only'])
    return PipelineQualityScore(value=5.0, reasons=['metadata only'])


def _provider_step_data(provider_config: dict[str, Any]) -> dict[str, Any]:
    return {
        'provider_configured': bool(provider_config.get('api_key')),
        'provider_name': provider_config.get('provider_name'),
        'provider_type': provider_config.get('provider_type'),
        'model_name': provider_config.get('model_name'),
    }


def _visual_provider_step_data(provider_config: dict[str, Any]) -> dict[str, Any]:
    return {
        'provider_configured': bool(provider_config.get('api_key')),
        'provider_name': provider_config.get('provider_name'),
        'provider_type': provider_config.get('provider_type'),
        'model_name': provider_config.get('model_name'),
    }


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _visual_summary_payload(
    visual_result: VisualUnderstandingResult,
    *,
    source_type: str,
    frame_count: int = 0,
    video_size_bytes: int | None = None,
) -> dict[str, Any]:
    evidence: dict[str, Any] = {'type': source_type}
    if frame_count:
        evidence['frame_count'] = frame_count
    if video_size_bytes is not None:
        evidence['video_size_bytes'] = video_size_bytes
    return {
        'summary_type': 'visual_context',
        'content': visual_result.summary or '',
        'provider_name': visual_result.provider_name,
        'model_name': visual_result.model_name,
        'version': 1,
        'evidence': [evidence],
    }


@dataclass(slots=True)
class BilibiliPipeline:
    """Subtitle-first Bilibili ingestion spike for OneRadar."""

    audio_extractor: AudioExtractor | None = None
    transcription_adapter: TranscriptionAdapter | None = None
    visual_video_extractor: VisualVideoExtractor | None = None
    visual_frame_extractor: VisualFrameExtractor | None = None
    visual_understanding_adapter: VisualUnderstandingAdapter | None = None

    def run(self, context: PipelineContext) -> PipelineRunResult:
        steps: list[PipelineStepResult] = []
        integration_config = dict((context.payload.get('integration_config') or {}).get('bilibili') or {})
        cookie_values = {
            'sessdata': integration_config.get('sessdata'),
            'bili_jct': integration_config.get('bili_jct'),
            'buvid3': integration_config.get('buvid3'),
        }
        video_ref = _normalize_video_ref(context.source_url, cookie_values=cookie_values)
        steps.append(
            PipelineStepResult(
                'normalize_url',
                bool(video_ref.bvid or video_ref.aid),
                'Bilibili URL normalized' if video_ref.bvid or video_ref.aid else 'Unsupported Bilibili URL',
                video_ref.to_dict(),
            )
        )
        if not video_ref.bvid and video_ref.aid is None:
            return PipelineRunResult(ok=False, steps=steps, data={'source_url': context.source_url})

        metadata_fetch = _fetch_metadata(video_ref, cookie_values=cookie_values)
        steps.append(
            PipelineStepResult(
                'fetch_metadata',
                metadata_fetch.ok,
                'Metadata fetched' if metadata_fetch.ok else (metadata_fetch.error_message or 'Metadata fetch failed'),
                metadata_fetch.to_dict(),
            )
        )
        if not metadata_fetch.ok:
            return PipelineRunResult(ok=False, steps=steps, data={'source_url': context.source_url, 'normalized_url': video_ref.normalized_url})

        metadata = _extract_video_metadata(video_ref, metadata_fetch.response_data)
        subtitle_catalog_fetch = _fetch_subtitle_catalog(video_ref, metadata, cookie_values=cookie_values)
        selected_track = _select_subtitle_track(subtitle_catalog_fetch.response_data) if subtitle_catalog_fetch.ok else None
        subtitle_transcript = (
            _fetch_subtitle_transcript(selected_track, video_ref.normalized_url, cookie_values=cookie_values)
            if selected_track and SUBTITLE_TRANSCRIPTS_ENABLED
            else None
        )
        transcript: BilibiliTranscriptPayload | None = None
        steps.append(
            PipelineStepResult(
                'fetch_subtitles',
                subtitle_transcript is not None,
                'Subtitle transcript fetched'
                if subtitle_transcript
                else 'Subtitle transcript is ignored by default; ASR is the canonical transcript source',
                {
                    'catalog': subtitle_catalog_fetch.to_dict(),
                    'selected_track': selected_track.to_dict() if selected_track else None,
                    'has_transcript': subtitle_transcript is not None,
                    'subtitle_transcripts_enabled': SUBTITLE_TRANSCRIPTS_ENABLED,
                },
            )
        )
        audio_extractor = self.audio_extractor or BilibiliAudioExtractor()
        audio_result = audio_extractor.extract(
            source_url=video_ref.normalized_url,
            referer=video_ref.normalized_url,
            cookie_values=cookie_values,
            item_id=context.item_id,
        )
        steps.append(
            PipelineStepResult(
                'extract_audio',
                audio_result.ok,
                'Audio extracted for ASR' if audio_result.ok else (audio_result.error_message or 'Audio extraction failed'),
                {
                    'tool_name': audio_result.tool_name,
                    'mime_type': audio_result.mime_type,
                    'has_audio': bool(audio_result.audio_path),
                    'metadata': audio_result.metadata,
                },
            )
        )
        provider_config = dict(context.payload.get('transcription_provider') or {})
        if not audio_result.ok or not audio_result.audio_path:
            steps.append(PipelineStepResult('transcribe_audio', False, 'Audio extraction did not produce an input file', {}))
        elif not is_transcription_configured(provider_config):
            steps.append(
                PipelineStepResult(
                    'transcribe_audio',
                    False,
                    'Transcription provider is not configured',
                    _provider_step_data(provider_config),
                )
            )
        else:
            adapter = self.transcription_adapter or select_transcription_adapter(provider_config)
            try:
                transcript = adapter.transcribe(
                    audio_path=audio_result.audio_path,
                    mime_type=audio_result.mime_type,
                    provider_config=provider_config,
                    language=str(context.payload.get('language') or 'zh-CN'),
                )
            except TranscriptionError as error:
                steps.append(
                    PipelineStepResult(
                        'transcribe_audio',
                        False,
                        str(error),
                        _provider_step_data(provider_config),
                    )
                )
            else:
                steps.append(
                    PipelineStepResult(
                        'transcribe_audio',
                        True,
                        'ASR transcript generated',
                        {
                            **_provider_step_data(provider_config),
                            'segment_count': len(transcript.segments),
                        },
                    )
                )

        visual_result: VisualUnderstandingResult | None = None
        visual_source_type = 'none'
        visual_frame_count = 0
        visual_video_size_bytes: int | None = None
        visual_config = dict(context.payload.get('visual_enhancement') or {})
        if visual_config.get('enabled') or integration_config.get('visual_enhancement_enabled'):
            visual_provider = dict(context.payload.get('visual_understanding_provider') or {})
            if not visual_provider.get('api_key') or not visual_provider.get('model_name') or not visual_provider.get('base_url'):
                steps.append(
                    PipelineStepResult(
                        'analyze_visual_context',
                        False,
                        'Visual understanding provider is not configured',
                        _visual_provider_step_data(visual_provider),
                    )
                )
            else:
                visual_adapter = self.visual_understanding_adapter or OpenAICompatibleVisualUnderstandingAdapter()
                video_extractor = self.visual_video_extractor or BilibiliLegacyVideoClipExtractor()
                video_result = video_extractor.extract_clip(
                    source_url=video_ref.normalized_url,
                    referer=video_ref.normalized_url,
                    cookie_values=cookie_values,
                    item_id=context.item_id,
                    duration_seconds=metadata.duration_seconds,
                )
                visual_video_size_bytes = _safe_int(video_result.metadata.get('size_bytes'))
                steps.append(
                    PipelineStepResult(
                        'extract_visual_video',
                        video_result.ok,
                        'Visual video clip extracted'
                        if video_result.ok
                        else (video_result.error_message or 'Visual video extraction failed'),
                        {
                            'tool_name': video_result.tool_name,
                            'mime_type': video_result.mime_type,
                            'has_video': bool(video_result.video_path),
                            'metadata': video_result.metadata,
                        },
                    )
                )
                if video_result.ok and video_result.video_path:
                    visual_result = visual_adapter.analyze_video(
                        video_path=video_result.video_path,
                        provider_config=visual_provider,
                        video_metadata=metadata.to_dict(),
                        transcript_text=transcript.full_text if transcript else metadata.description,
                        language=(transcript.language if transcript else None)
                        or str(context.payload.get('language') or 'zh-CN'),
                    )
                    visual_source_type = 'sampled_video_clip' if visual_result.ok else 'none'
                    steps.append(
                        PipelineStepResult(
                            'analyze_visual_video',
                            visual_result.ok,
                            'Visual context generated from video'
                            if visual_result.ok
                            else (visual_result.error_message or 'Visual video analysis failed'),
                            {
                                **_visual_provider_step_data(visual_provider),
                                'video_size_bytes': visual_video_size_bytes,
                            },
                        )
                    )

                if visual_result is None or not visual_result.ok:
                    frame_extractor = self.visual_frame_extractor or BilibiliLegacyFrameExtractor()
                    frame_result = frame_extractor.extract_frames(
                        source_url=video_ref.normalized_url,
                        referer=video_ref.normalized_url,
                        cookie_values=cookie_values,
                        item_id=context.item_id,
                        duration_seconds=metadata.duration_seconds,
                    )
                    visual_frame_count = len(frame_result.frame_paths)
                    steps.append(
                        PipelineStepResult(
                            'extract_visual_frames',
                            frame_result.ok,
                            'Visual frames extracted'
                            if frame_result.ok
                            else (frame_result.error_message or 'Visual frame extraction failed'),
                            {
                                'tool_name': frame_result.tool_name,
                                'frame_count': visual_frame_count,
                                'metadata': frame_result.metadata,
                            },
                        )
                    )
                else:
                    frame_result = None

                if frame_result is not None and frame_result.ok and frame_result.frame_paths:
                    visual_result = visual_adapter.analyze(
                        frame_paths=frame_result.frame_paths,
                        provider_config=visual_provider,
                        video_metadata=metadata.to_dict(),
                        transcript_text=transcript.full_text if transcript else metadata.description,
                        language=(transcript.language if transcript else None)
                        or str(context.payload.get('language') or 'zh-CN'),
                    )
                    visual_source_type = 'sampled_video_frames' if visual_result.ok else 'none'
                    steps.append(
                        PipelineStepResult(
                            'analyze_visual_context',
                            visual_result.ok,
                            'Visual context generated' if visual_result.ok else (visual_result.error_message or 'Visual analysis failed'),
                            {
                                **_visual_provider_step_data(visual_provider),
                                'frame_count': visual_frame_count,
                            },
                        )
                    )
                elif frame_result is not None:
                    steps.append(PipelineStepResult('analyze_visual_context', False, 'Skipped because no visual frames were extracted', {}))
        else:
            steps.append(PipelineStepResult('analyze_visual_context', False, 'Skipped because visual enhancement is disabled', {}))

        quality = _quality_score(transcript, metadata.description)
        parsed_plain_text = transcript.full_text if transcript else metadata.description or metadata.title
        structured_blocks = _transcript_blocks(transcript) if transcript else _description_blocks(metadata.description or metadata.title)
        summaries = []
        if visual_result is not None and visual_result.ok and visual_result.summary:
            summaries.append(
                _visual_summary_payload(
                    visual_result,
                    source_type=visual_source_type,
                    frame_count=visual_frame_count,
                    video_size_bytes=visual_video_size_bytes,
                )
            )
        parsed_document = {
            'parser_name': 'bilibili_asr_first',
            'parser_version': 'v0_spike',
            'title': metadata.title,
            'excerpt': metadata.description[:280] if metadata.description else None,
            'plain_text': parsed_plain_text,
            'structured_blocks': [
                {
                    'type': block.block_type,
                    'text': block.text,
                    'order': block.order,
                    'data': block.data,
                }
                for block in structured_blocks
            ],
        }
        persistable = {
            'content_item': {
                'title': metadata.title,
                'subtitle': metadata.part_title,
                'author_name': metadata.owner_name,
                'author_id': metadata.owner_id,
                'cover_url': metadata.cover_url,
                'duration_seconds': metadata.duration_seconds,
                'language': transcript.language if transcript else 'zh-CN',
                'published_at': metadata.published_at,
                'raw_meta': {
                    'site_name': 'Bilibili',
                    'host': urlsplit(video_ref.normalized_url).netloc,
                    'author_name': metadata.owner_name,
                    'published_at': metadata.published_at,
                    'bvid': metadata.bvid,
                    'aid': metadata.aid,
                    'cid': metadata.cid,
                    'page': metadata.page,
                    'description': metadata.description,
                    'cover_url': metadata.cover_url,
                    'duration_seconds': metadata.duration_seconds,
                    'part_title': metadata.part_title,
                    'subtitle_track': selected_track.to_dict() if selected_track else None,
                    'content_hash': f"bilibili:{metadata.bvid or metadata.aid}:{metadata.cid or 'nocid'}",
                    'transcript_status': transcript.transcript_type if transcript else 'unavailable',
                    'visual_enhancement_status': 'completed' if summaries else ('enabled' if visual_config.get('enabled') or integration_config.get('visual_enhancement_enabled') else 'disabled'),
                    'visual_enhancement': {
                        'provider_name': visual_result.provider_name if visual_result else None,
                        'model_name': visual_result.model_name if visual_result else None,
                        'source_type': visual_source_type,
                        'frame_count': visual_frame_count,
                        'video_size_bytes': visual_video_size_bytes,
                    },
                },
            },
            'parsed_document': parsed_document,
            'transcript': transcript.to_dict() if transcript else None,
            'summaries': summaries,
            'quality': asdict(quality),
        }
        result = {
            'source_url': context.source_url,
            'normalized_url': video_ref.normalized_url,
            'host': urlsplit(video_ref.normalized_url).netloc,
            'site_name': 'Bilibili',
            'fetch': {
                'mode': 'bilibili_api',
                'status_code': 200,
                'content_type': 'application/json',
                'final_url': video_ref.normalized_url,
                'error_message': None,
            },
            'video': metadata.to_dict(),
            'selected_subtitle': selected_track.to_dict() if selected_track else None,
            'integration': {
                'bilibili_cookie_enabled': bool(integration_config.get('is_enabled')),
                'cookie_keys_present': [key for key, value in cookie_values.items() if value],
            },
            'quality': asdict(quality),
            'persistable': persistable,
        }
        steps.append(
            PipelineStepResult(
                'build_transcript_view',
                transcript is not None,
                'Transcript and reader payload prepared' if transcript else 'Metadata-only reader payload prepared',
                {
                    'transcript_available': transcript is not None,
                    'quality': asdict(quality),
                },
            )
        )
        return PipelineRunResult(ok=bool(transcript), steps=steps, data=result)
