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
        return PipelineQualityScore(value=85.0, reasons=['subtitle transcript available'])
    if description.strip():
        return PipelineQualityScore(value=40.0, reasons=['metadata description fallback only'])
    return PipelineQualityScore(value=5.0, reasons=['metadata only'])


@dataclass(slots=True)
class BilibiliPipeline:
    """Subtitle-first Bilibili ingestion spike for OneRadar."""

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
        transcript = _fetch_subtitle_transcript(selected_track, video_ref.normalized_url, cookie_values=cookie_values) if selected_track else None
        steps.append(
            PipelineStepResult(
                'fetch_subtitles',
                transcript is not None,
                'Subtitle transcript fetched' if transcript else 'No subtitle transcript available',
                {
                    'catalog': subtitle_catalog_fetch.to_dict(),
                    'selected_track': selected_track.to_dict() if selected_track else None,
                    'has_transcript': transcript is not None,
                },
            )
        )
        steps.append(PipelineStepResult('extract_audio', False, 'Audio fallback not implemented in this spike', {}))
        steps.append(PipelineStepResult('transcribe_audio', False, 'ASR fallback not implemented in this spike', {}))

        quality = _quality_score(transcript, metadata.description)
        parsed_plain_text = transcript.full_text if transcript else metadata.description or metadata.title
        structured_blocks = _transcript_blocks(transcript) if transcript else _description_blocks(metadata.description or metadata.title)
        parsed_document = {
            'parser_name': 'bilibili_subtitle_first',
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
                    'transcript_status': 'subtitle' if transcript else 'unavailable',
                },
            },
            'parsed_document': parsed_document,
            'transcript': transcript.to_dict() if transcript else None,
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
        return PipelineRunResult(ok=bool(transcript or metadata.description or metadata.title), steps=steps, data=result)
