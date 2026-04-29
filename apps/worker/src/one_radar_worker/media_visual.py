from __future__ import annotations

from dataclasses import dataclass, field
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen
from uuid import UUID

from .media_audio import (
    _bilibili_api_data,
    _bilibili_browser_headers,
    _extract_bvid,
    _read_json_url,
    _redact_sensitive,
)


@dataclass(slots=True)
class VisualFrameExtractionResult:
    ok: bool
    frame_paths: list[str] = field(default_factory=list)
    tool_name: str = "bilibili-legacy-frames"
    error_message: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class VisualVideoExtractionResult:
    ok: bool
    video_path: str | None = None
    mime_type: str | None = None
    tool_name: str = "bilibili-legacy-video-clip"
    error_message: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class VisualUnderstandingResult:
    ok: bool
    summary: str | None = None
    provider_name: str | None = None
    model_name: str | None = None
    error_message: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


class VisualFrameExtractor(Protocol):
    def extract_frames(
        self,
        *,
        source_url: str,
        referer: str,
        cookie_values: dict[str, str | None],
        item_id: UUID,
        duration_seconds: int | None,
    ) -> VisualFrameExtractionResult: ...


class VisualVideoExtractor(Protocol):
    def extract_clip(
        self,
        *,
        source_url: str,
        referer: str,
        cookie_values: dict[str, str | None],
        item_id: UUID,
        duration_seconds: int | None,
    ) -> VisualVideoExtractionResult: ...


class VisualUnderstandingAdapter(Protocol):
    def analyze_video(
        self,
        *,
        video_path: str,
        provider_config: dict[str, Any],
        video_metadata: dict[str, Any],
        transcript_text: str,
        language: str | None,
    ) -> VisualUnderstandingResult: ...

    def analyze(
        self,
        *,
        frame_paths: list[str],
        provider_config: dict[str, Any],
        video_metadata: dict[str, Any],
        transcript_text: str,
        language: str | None,
    ) -> VisualUnderstandingResult: ...


def _fetch_lowest_bilibili_video_track(
    *,
    source_url: str,
    referer: str,
    cookie_values: dict[str, str | None],
    timeout_seconds: int,
) -> tuple[str, dict[str, object]]:
    bvid = _extract_bvid(source_url)
    if bvid is None:
        raise ValueError("Could not find a Bilibili BV id in the source URL")

    headers = _bilibili_browser_headers(referer=referer, cookie_values=cookie_values)
    view_url = "https://api.bilibili.com/x/web-interface/view?" + urlencode({"bvid": bvid})
    view_data = _bilibili_api_data(_read_json_url(view_url, headers, timeout_seconds))
    cid = view_data.get("cid")
    if cid is None:
        raise ValueError("Bilibili metadata did not include cid")

    play_url = "https://api.bilibili.com/x/player/playurl?" + urlencode(
        {
            "bvid": bvid,
            "cid": str(cid),
            "fnval": "16",
            "qn": "16",
            "fourk": "0",
        }
    )
    play_data = _bilibili_api_data(_read_json_url(play_url, headers, timeout_seconds))
    dash = play_data.get("dash")
    video_tracks = dash.get("video") if isinstance(dash, dict) else None
    if not isinstance(video_tracks, list) or not video_tracks:
        raise ValueError("Bilibili playurl did not return dash video")

    video_track = min(
        (track for track in video_tracks if isinstance(track, dict)),
        key=lambda track: int(track.get("bandwidth") or 0),
        default=None,
    )
    if video_track is None:
        raise ValueError("Bilibili playurl returned invalid video tracks")
    video_url = video_track.get("baseUrl") or video_track.get("base_url")
    if not isinstance(video_url, str) or not video_url:
        raise ValueError("Bilibili video track did not include a URL")
    return video_url, video_track


@dataclass(slots=True)
class BilibiliLegacyVideoClipExtractor:
    ffmpeg_executable: str | None = None
    output_root: Path | None = None
    max_clip_seconds: int = 90
    timeout_seconds: int = 900

    def extract_clip(
        self,
        *,
        source_url: str,
        referer: str,
        cookie_values: dict[str, str | None],
        item_id: UUID,
        duration_seconds: int | None,
    ) -> VisualVideoExtractionResult:
        root = self.output_root or Path(os.getenv("ONERADAR_MEDIA_CACHE_ROOT", tempfile.gettempdir()))
        output_dir = root / "oneradar-media" / str(item_id) / "bilibili-video-clip"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "visual_clip.mp4"
        headers = _bilibili_browser_headers(referer=referer, cookie_values=cookie_values)

        try:
            video_url, video_track = _fetch_lowest_bilibili_video_track(
                source_url=source_url,
                referer=referer,
                cookie_values=cookie_values,
                timeout_seconds=self.timeout_seconds,
            )
            clip_seconds = min(
                self.max_clip_seconds,
                max(1, int(duration_seconds or self.max_clip_seconds)),
            )
            ffmpeg = self.ffmpeg_executable or os.getenv("ONERADAR_FFMPEG_BIN", "ffmpeg")
            header_lines = "\r\n".join(f"{key}: {value}" for key, value in headers.items()) + "\r\n"
            command = [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-headers",
                header_lines,
                "-i",
                video_url,
                "-t",
                str(clip_seconds),
                "-vf",
                "fps=1,scale=640:-2",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "32",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
            completed = subprocess.run(
                command,
                capture_output=True,
                check=False,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
            )
        except (
            OSError,
            subprocess.TimeoutExpired,
            HTTPError,
            URLError,
            json.JSONDecodeError,
            ValueError,
        ) as exc:
            return VisualVideoExtractionResult(
                ok=False,
                error_message=_redact_sensitive(str(exc), cookie_values),
            )

        if completed.returncode != 0:
            message = (completed.stderr or completed.stdout or "ffmpeg failed").strip()
            return VisualVideoExtractionResult(
                ok=False,
                error_message=_redact_sensitive(message, cookie_values),
            )
        if not output_path.exists():
            return VisualVideoExtractionResult(ok=False, error_message="ffmpeg did not produce a video clip")

        return VisualVideoExtractionResult(
            ok=True,
            video_path=str(output_path),
            mime_type="video/mp4",
            metadata={
                "clip_seconds": clip_seconds,
                "video_id": video_track.get("id"),
                "bandwidth": video_track.get("bandwidth"),
                "size_bytes": output_path.stat().st_size,
            },
        )


@dataclass(slots=True)
class BilibiliLegacyFrameExtractor:
    ffmpeg_executable: str | None = None
    output_root: Path | None = None
    max_frames: int = 8
    timeout_seconds: int = 900

    def extract_frames(
        self,
        *,
        source_url: str,
        referer: str,
        cookie_values: dict[str, str | None],
        item_id: UUID,
        duration_seconds: int | None,
    ) -> VisualFrameExtractionResult:
        root = self.output_root or Path(os.getenv("ONERADAR_MEDIA_CACHE_ROOT", tempfile.gettempdir()))
        output_dir = root / "oneradar-media" / str(item_id) / "bilibili-frames"
        output_dir.mkdir(parents=True, exist_ok=True)
        headers = _bilibili_browser_headers(referer=referer, cookie_values=cookie_values)

        try:
            video_url, video_track = _fetch_lowest_bilibili_video_track(
                source_url=source_url,
                referer=referer,
                cookie_values=cookie_values,
                timeout_seconds=self.timeout_seconds,
            )
            interval = _sampling_interval_seconds(duration_seconds=duration_seconds, max_frames=self.max_frames)
            ffmpeg = self.ffmpeg_executable or os.getenv("ONERADAR_FFMPEG_BIN", "ffmpeg")
            header_lines = "\r\n".join(f"{key}: {value}" for key, value in headers.items()) + "\r\n"
            command = [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-headers",
                header_lines,
                "-i",
                video_url,
                "-vf",
                f"fps=1/{interval},scale=960:-2",
                "-frames:v",
                str(self.max_frames),
                str(output_dir / "frame_%03d.jpg"),
            ]
            completed = subprocess.run(
                command,
                capture_output=True,
                check=False,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
            )
        except (
            OSError,
            subprocess.TimeoutExpired,
            HTTPError,
            URLError,
            json.JSONDecodeError,
            ValueError,
        ) as exc:
            return VisualFrameExtractionResult(
                ok=False,
                error_message=_redact_sensitive(str(exc), cookie_values),
            )

        if completed.returncode != 0:
            message = (completed.stderr or completed.stdout or "ffmpeg failed").strip()
            return VisualFrameExtractionResult(ok=False, error_message=_redact_sensitive(message, cookie_values))

        frame_paths = [str(path) for path in sorted(output_dir.glob("frame_*.jpg")) if path.is_file()]
        if not frame_paths:
            return VisualFrameExtractionResult(ok=False, error_message="ffmpeg did not produce visual frames")

        return VisualFrameExtractionResult(
            ok=True,
            frame_paths=frame_paths,
            metadata={
                "frame_count": len(frame_paths),
                "sampling_interval_seconds": interval,
                "video_id": video_track.get("id"),
                "bandwidth": video_track.get("bandwidth"),
            },
        )


@dataclass(slots=True)
class OpenAICompatibleVisualUnderstandingAdapter:
    timeout_seconds: int = 900
    max_transcript_chars: int = 6000

    def analyze_video(
        self,
        *,
        video_path: str,
        provider_config: dict[str, Any],
        video_metadata: dict[str, Any],
        transcript_text: str,
        language: str | None,
    ) -> VisualUnderstandingResult:
        api_key = str(provider_config.get("api_key") or "").strip()
        model_name = str(provider_config.get("model_name") or "").strip()
        if not api_key:
            return VisualUnderstandingResult(ok=False, error_message="visual provider API key is not configured")
        if not model_name:
            return VisualUnderstandingResult(ok=False, error_message="visual understanding model is not configured")
        file_path = Path(video_path)
        if not file_path.exists():
            return VisualUnderstandingResult(ok=False, error_message="visual video clip does not exist")

        content = [
            {
                "type": "video_url",
                "video_url": {
                    "url": _video_data_url(file_path),
                },
            },
            {
                "type": "text",
                "text": _visual_prompt(
                    video_metadata=video_metadata,
                    transcript_text=transcript_text[: self.max_transcript_chars],
                    language=language,
                ),
            },
        ]
        response = self._chat(provider_config=provider_config, api_key=api_key, model_name=model_name, content=content)
        if not response.ok:
            return response
        response.metadata["video_size_bytes"] = file_path.stat().st_size
        return response

    def analyze(
        self,
        *,
        frame_paths: list[str],
        provider_config: dict[str, Any],
        video_metadata: dict[str, Any],
        transcript_text: str,
        language: str | None,
    ) -> VisualUnderstandingResult:
        api_key = str(provider_config.get("api_key") or "").strip()
        model_name = str(provider_config.get("model_name") or "").strip()
        if not api_key:
            return VisualUnderstandingResult(ok=False, error_message="visual provider API key is not configured")
        if not model_name:
            return VisualUnderstandingResult(ok=False, error_message="visual understanding model is not configured")
        if not frame_paths:
            return VisualUnderstandingResult(ok=False, error_message="visual frame list is empty")

        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": _visual_prompt(
                    video_metadata=video_metadata,
                    transcript_text=transcript_text[: self.max_transcript_chars],
                    language=language,
                ),
            }
        ]
        for frame_path in frame_paths:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": _jpeg_data_url(Path(frame_path)),
                    },
                }
            )

        response = self._chat(provider_config=provider_config, api_key=api_key, model_name=model_name, content=content)
        if response.ok:
            response.metadata["frame_count"] = len(frame_paths)
        return response

    def _chat(
        self,
        *,
        provider_config: dict[str, Any],
        api_key: str,
        model_name: str,
        content: list[dict[str, Any]],
    ) -> VisualUnderstandingResult:
        payload = _chat_payload(model_name=model_name, content=content)
        request = Request(
            _chat_endpoint(str(provider_config.get("base_url") or "")),
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8", errors="replace")
            response_payload = json.loads(raw)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            return VisualUnderstandingResult(ok=False, error_message=str(exc))

        summary = _extract_chat_text(response_payload)
        if not summary:
            return VisualUnderstandingResult(ok=False, error_message="visual provider returned an empty response")
        return VisualUnderstandingResult(
            ok=True,
            summary=summary,
            provider_name=str(provider_config.get("provider_name") or ""),
            model_name=model_name,
            metadata={},
        )


def _sampling_interval_seconds(*, duration_seconds: int | None, max_frames: int) -> int:
    if not duration_seconds or duration_seconds <= 0:
        return 30
    return max(10, int(duration_seconds / max(max_frames, 1)))


def _chat_endpoint(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    if not normalized:
        raise ValueError("visual provider base URL is not configured")
    if normalized.endswith("/chat/completions"):
        return normalized
    return urljoin(f"{normalized}/", "chat/completions")


def _jpeg_data_url(path: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _video_data_url(path: Path) -> str:
    return "data:video/mp4;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _chat_payload(*, model_name: str, content: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "model": model_name,
        "messages": [
            {
                "role": "user",
                "content": content,
            }
        ],
        "temperature": 0.2,
        "max_tokens": 1200,
    }


def _visual_prompt(*, video_metadata: dict[str, Any], transcript_text: str, language: str | None) -> str:
    title = str(video_metadata.get("title") or "Bilibili 视频")
    description = str(video_metadata.get("description") or "")
    return (
        "你是 OneRadar 的视频视觉理解模块。请结合抽样画面、视频元数据和已有字幕/转写，"
        "补充文字转写无法覆盖的画面信息。重点识别：PPT/代码/图表/屏幕内容、人物动作、"
        "演示步骤、镜头变化、画面中的关键实体。不要复述完整字幕，只输出可用于后续摘要的大纲式视觉补充。\n\n"
        f"输出语言：{language or 'zh-CN'}\n"
        f"标题：{title}\n"
        f"简介：{description[:1000]}\n"
        f"字幕/转写节选：\n{transcript_text}"
    )


def _extract_chat_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [str(part.get("text") or "").strip() for part in content if isinstance(part, dict)]
        return "\n".join(part for part in parts if part).strip()
    return ""
