from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Protocol, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import UUID


@dataclass(slots=True)
class AudioExtractionResult:
    ok: bool
    audio_path: str | None = None
    mime_type: str | None = None
    tool_name: str = "yt-dlp"
    error_message: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


class AudioExtractor(Protocol):
    def extract(
        self,
        *,
        source_url: str,
        referer: str,
        cookie_values: dict[str, str | None],
        item_id: UUID,
    ) -> AudioExtractionResult: ...


def _cookie_header(cookie_values: dict[str, str | None]) -> str | None:
    parts = []
    for key, value in {
        "SESSDATA": cookie_values.get("sessdata"),
        "bili_jct": cookie_values.get("bili_jct"),
        "buvid3": cookie_values.get("buvid3"),
    }.items():
        if value:
            parts.append(f"{key}={value}")
    return "; ".join(parts) if parts else None


def _redact_sensitive(text: str, cookie_values: dict[str, str | None]) -> str:
    redacted = text
    for value in cookie_values.values():
        if value:
            redacted = redacted.replace(value, "[redacted]")
    return redacted


def _write_netscape_cookie_file(cookie_values: dict[str, str | None], directory: Path) -> Path | None:
    rows = [
        "# Netscape HTTP Cookie File",
    ]
    has_cookie = False
    for name, value in {
        "SESSDATA": cookie_values.get("sessdata"),
        "bili_jct": cookie_values.get("bili_jct"),
        "buvid3": cookie_values.get("buvid3"),
    }.items():
        if not value:
            continue
        has_cookie = True
        rows.append(f".bilibili.com\tTRUE\t/\tFALSE\t0\t{name}\t{value}")
    if not has_cookie:
        return None

    cookie_file = tempfile.NamedTemporaryFile(
        "w",
        delete=False,
        dir=directory,
        encoding="utf-8",
        newline="\n",
        prefix="oneradar-bilibili-",
        suffix=".cookies.txt",
    )
    with cookie_file:
        cookie_file.write("\n".join(rows))
        cookie_file.write("\n")
    return Path(cookie_file.name)


def _write_bbdown_config_file(cookie_values: dict[str, str | None], directory: Path) -> Path | None:
    lines = [
        "--audio-only",
        "--hide-streams",
        "--file-pattern",
        "audio",
    ]
    cookie_header = _cookie_header(cookie_values)
    if cookie_header:
        lines.extend(["--cookie", cookie_header])

    config_file = tempfile.NamedTemporaryFile(
        "w",
        delete=False,
        dir=directory,
        encoding="utf-8",
        newline="\n",
        prefix="oneradar-bbdown-",
        suffix=".config",
    )
    with config_file:
        config_file.write("\n".join(lines))
        config_file.write("\n")
    return Path(config_file.name)


def _guess_mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".m4a", ".mp4"}:
        return "audio/mp4"
    if suffix == ".mp3":
        return "audio/mpeg"
    if suffix == ".wav":
        return "audio/wav"
    if suffix == ".webm":
        return "audio/webm"
    return "application/octet-stream"


def _bilibili_browser_headers(
    *,
    referer: str,
    cookie_values: dict[str, str | None],
) -> dict[str, str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": referer,
    }
    cookie_header = _cookie_header(cookie_values)
    if cookie_header:
        headers["Cookie"] = cookie_header
    return headers


def _extract_bvid(source_url: str) -> str | None:
    match = re.search(r"(BV[0-9A-Za-z]+)", source_url)
    return match.group(1) if match else None


def _read_json_url(url: str, headers: dict[str, str], timeout_seconds: int) -> dict[str, object]:
    request = Request(url, headers=headers)
    with urlopen(request, timeout=timeout_seconds) as response:
        body = response.read().decode("utf-8", "replace")
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError("Bilibili returned a non-object JSON payload")
    return payload


def _bilibili_api_data(payload: dict[str, object]) -> dict[str, object]:
    if payload.get("code") != 0:
        raise ValueError(f"Bilibili API returned code {payload.get('code')}: {payload.get('message')}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("Bilibili API response did not include data")
    return data


def _latest_audio_file(output_dir: Path) -> Path | None:
    audio_suffixes = {".m4a", ".mp3", ".wav", ".webm", ".aac", ".flac"}
    candidates = sorted(
        [path for path in output_dir.iterdir() if path.is_file() and path.suffix.lower() in audio_suffixes],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


@dataclass(slots=True)
class BilibiliLegacyAudioExtractor:
    ffmpeg_executable: str | None = None
    output_root: Path | None = None
    timeout_seconds: int = 900

    def extract(
        self,
        *,
        source_url: str,
        referer: str,
        cookie_values: dict[str, str | None],
        item_id: UUID,
    ) -> AudioExtractionResult:
        bvid = _extract_bvid(source_url)
        if bvid is None:
            return AudioExtractionResult(
                ok=False,
                error_message="Could not find a Bilibili BV id in the source URL",
                tool_name="bilibili-legacy-playurl",
            )

        root = self.output_root or Path(os.getenv("ONERADAR_MEDIA_CACHE_ROOT", tempfile.gettempdir()))
        output_dir = root / "oneradar-media" / str(item_id) / "bilibili-legacy"
        output_dir.mkdir(parents=True, exist_ok=True)
        headers = _bilibili_browser_headers(referer=referer, cookie_values=cookie_values)

        raw_audio_path = output_dir / "audio.m4s"
        try:
            view_url = "https://api.bilibili.com/x/web-interface/view?" + urlencode({"bvid": bvid})
            view_data = _bilibili_api_data(_read_json_url(view_url, headers, self.timeout_seconds))
            cid = view_data.get("cid")
            if cid is None:
                return AudioExtractionResult(
                    ok=False,
                    error_message="Bilibili metadata did not include cid",
                    tool_name="bilibili-legacy-playurl",
                )

            play_url = "https://api.bilibili.com/x/player/playurl?" + urlencode(
                {
                    "bvid": bvid,
                    "cid": str(cid),
                    "fnval": "16",
                    "qn": "64",
                    "fourk": "1",
                }
            )
            play_data = _bilibili_api_data(_read_json_url(play_url, headers, self.timeout_seconds))
            dash = play_data.get("dash")
            audio_tracks = dash.get("audio") if isinstance(dash, dict) else None
            if not isinstance(audio_tracks, list) or not audio_tracks:
                return AudioExtractionResult(
                    ok=False,
                    error_message="Bilibili legacy playurl did not return dash audio",
                    tool_name="bilibili-legacy-playurl",
                )
            audio_track = audio_tracks[0]
            if not isinstance(audio_track, dict):
                return AudioExtractionResult(
                    ok=False,
                    error_message="Bilibili legacy playurl returned an invalid audio track",
                    tool_name="bilibili-legacy-playurl",
                )
            audio_url = audio_track.get("baseUrl") or audio_track.get("base_url")
            if not isinstance(audio_url, str) or not audio_url:
                return AudioExtractionResult(
                    ok=False,
                    error_message="Bilibili legacy playurl audio track did not include a URL",
                    tool_name="bilibili-legacy-playurl",
                )

            with urlopen(Request(audio_url, headers=headers), timeout=self.timeout_seconds) as response:
                raw_audio_path.write_bytes(response.read())

            audio_path = output_dir / "audio.m4a"
            ffmpeg = self.ffmpeg_executable or os.getenv("ONERADAR_FFMPEG_BIN", "ffmpeg")
            command = [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(raw_audio_path),
                "-c",
                "copy",
                str(audio_path),
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
            raw_audio_path.unlink(missing_ok=True)
            return AudioExtractionResult(
                ok=False,
                error_message=_redact_sensitive(str(exc), cookie_values),
                tool_name="bilibili-legacy-playurl",
            )

        raw_audio_path.unlink(missing_ok=True)
        if completed.returncode != 0:
            message = (completed.stderr or completed.stdout or "ffmpeg failed").strip()
            return AudioExtractionResult(
                ok=False,
                error_message=_redact_sensitive(message, cookie_values),
                tool_name="bilibili-legacy-playurl",
            )
        if not audio_path.exists():
            return AudioExtractionResult(
                ok=False,
                error_message="Bilibili legacy extractor did not produce an audio file",
                tool_name="bilibili-legacy-playurl",
            )

        return AudioExtractionResult(
            ok=True,
            audio_path=str(audio_path),
            mime_type=_guess_mime_type(audio_path),
            tool_name="bilibili-legacy-playurl",
            metadata={
                "audio_id": audio_track.get("id"),
                "bandwidth": audio_track.get("bandwidth"),
                "size_bytes": audio_path.stat().st_size,
            },
        )


@dataclass(slots=True)
class BbDownAudioExtractor:
    executable: str | None = None
    output_root: Path | None = None
    timeout_seconds: int = 900

    def extract(
        self,
        *,
        source_url: str,
        referer: str,
        cookie_values: dict[str, str | None],
        item_id: UUID,
    ) -> AudioExtractionResult:
        executable = self.executable or os.getenv("ONERADAR_BBDOWN_BIN", "BBDown")
        root = self.output_root or Path(os.getenv("ONERADAR_MEDIA_CACHE_ROOT", tempfile.gettempdir()))
        output_dir = root / "oneradar-media" / str(item_id) / "bbdown"
        output_dir.mkdir(parents=True, exist_ok=True)
        config_path = _write_bbdown_config_file(cookie_values, output_dir)
        command = [executable]
        if config_path is not None:
            command.extend(["--config-file", str(config_path)])
        command.append(source_url)
        env = dict(os.environ)
        env.setdefault("DOTNET_ROLL_FORWARD", "Major")

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                check=False,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                cwd=output_dir,
                env=env,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return AudioExtractionResult(ok=False, error_message=str(exc), tool_name=executable)
        finally:
            if config_path is not None:
                config_path.unlink(missing_ok=True)

        if completed.returncode != 0:
            message = (completed.stderr or completed.stdout or "BBDown failed").strip()
            return AudioExtractionResult(
                ok=False,
                error_message=_redact_sensitive(message, cookie_values),
                tool_name=executable,
            )

        audio_path = _latest_audio_file(output_dir)
        if audio_path is None:
            return AudioExtractionResult(ok=False, error_message="BBDown did not produce an audio file", tool_name=executable)
        return AudioExtractionResult(
            ok=True,
            audio_path=str(audio_path),
            mime_type=_guess_mime_type(audio_path),
            tool_name=executable,
            metadata={"size_bytes": audio_path.stat().st_size},
        )


@dataclass(slots=True)
class YtDlpAudioExtractor:
    executable: str | None = None
    output_root: Path | None = None
    timeout_seconds: int = 900

    def extract(
        self,
        *,
        source_url: str,
        referer: str,
        cookie_values: dict[str, str | None],
        item_id: UUID,
    ) -> AudioExtractionResult:
        executable = self.executable or os.getenv("ONERADAR_YTDLP_BIN", "yt-dlp")
        root = self.output_root or Path(os.getenv("ONERADAR_MEDIA_CACHE_ROOT", tempfile.gettempdir()))
        output_dir = root / "oneradar-media" / str(item_id) / "yt-dlp"
        output_dir.mkdir(parents=True, exist_ok=True)
        cookie_path = _write_netscape_cookie_file(cookie_values, output_dir)

        command = [
            executable,
            "--no-playlist",
            "--extract-audio",
            "--audio-format",
            "m4a",
            "--paths",
            str(output_dir),
            "--output",
            "%(id)s.%(ext)s",
            "--print",
            "after_move:filepath",
            "--referer",
            referer,
        ]
        if cookie_path is not None:
            command.extend(["--cookies", str(cookie_path)])
        command.append(source_url)

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                check=False,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return AudioExtractionResult(ok=False, error_message=str(exc), tool_name=executable)
        finally:
            if cookie_path is not None:
                cookie_path.unlink(missing_ok=True)

        if completed.returncode != 0:
            return AudioExtractionResult(
                ok=False,
                error_message=_redact_sensitive((completed.stderr or completed.stdout or "yt-dlp failed").strip(), cookie_values),
                tool_name=executable,
            )

        candidates = [
            Path(line.strip())
            for line in completed.stdout.splitlines()
            if line.strip() and Path(line.strip()).exists()
        ]
        if not candidates:
            latest = _latest_audio_file(output_dir)
            candidates = [latest] if latest is not None else []
        if not candidates:
            return AudioExtractionResult(ok=False, error_message="yt-dlp did not produce an audio file", tool_name=executable)

        audio_path = candidates[0]
        return AudioExtractionResult(
            ok=True,
            audio_path=str(audio_path),
            mime_type=_guess_mime_type(audio_path),
            tool_name=executable,
            metadata={"size_bytes": audio_path.stat().st_size},
        )


@dataclass(slots=True)
class BilibiliAudioExtractor:
    extractors: Sequence[AudioExtractor] = field(
        default_factory=lambda: (
            BbDownAudioExtractor(),
            BilibiliLegacyAudioExtractor(),
            YtDlpAudioExtractor(),
        )
    )

    def extract(
        self,
        *,
        source_url: str,
        referer: str,
        cookie_values: dict[str, str | None],
        item_id: UUID,
    ) -> AudioExtractionResult:
        failures: list[str] = []
        for extractor in self.extractors:
            result = extractor.extract(
                source_url=source_url,
                referer=referer,
                cookie_values=cookie_values,
                item_id=item_id,
            )
            if result.ok:
                return result
            failures.append(f"{result.tool_name}: {result.error_message or 'failed'}")
        return AudioExtractionResult(
            ok=False,
            tool_name="bilibili-audio",
            error_message="; ".join(failures) or "audio extraction failed",
        )
