from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
from uuid import uuid4

from one_radar_worker.media_audio import (
    AudioExtractionResult,
    BilibiliAudioExtractor,
    BilibiliLegacyAudioExtractor,
    BbDownAudioExtractor,
    YtDlpAudioExtractor,
)


def test_yt_dlp_uses_temporary_cookie_file_without_leaking_cookie_args(monkeypatch):
    observed: dict[str, object] = {}
    test_root = Path(".tmp-media-audio-tests") / str(uuid4())
    test_root.mkdir(parents=True, exist_ok=True)

    def fake_run(command, *, capture_output, check, text, encoding, errors, timeout):
        assert capture_output is True
        assert check is False
        assert text is True
        assert encoding == "utf-8"
        assert errors == "replace"
        assert timeout == 60
        observed["command"] = command
        cookie_path = Path(command[command.index("--cookies") + 1])
        observed["cookie_path"] = cookie_path
        observed["cookie_text"] = cookie_path.read_text(encoding="utf-8")
        output_path = test_root / "oneradar-media" / str(item_id) / "yt-dlp" / "audio.m4a"
        output_path.write_bytes(b"audio")
        return subprocess.CompletedProcess(command, 0, stdout=f"{output_path}\n", stderr="")

    item_id = uuid4()
    monkeypatch.setattr(subprocess, "run", fake_run)

    try:
        result = YtDlpAudioExtractor(
            executable="yt-dlp",
            output_root=test_root,
            timeout_seconds=60,
        ).extract(
            source_url="https://www.bilibili.com/video/BV1test",
            referer="https://www.bilibili.com/video/BV1test",
            cookie_values={
                "sessdata": "secret-sessdata",
                "bili_jct": "secret-jct",
                "buvid3": "secret-buvid",
            },
            item_id=item_id,
        )

        command_text = " ".join(str(part) for part in observed["command"])
        assert result.ok is True
        assert "--cookies" in observed["command"]
        assert "secret-sessdata" not in command_text
        assert "secret-jct" not in command_text
        assert "secret-buvid" not in command_text
        assert "secret-sessdata" in str(observed["cookie_text"])
        assert not Path(observed["cookie_path"]).exists()
    finally:
        shutil.rmtree(test_root, ignore_errors=True)


def test_bilibili_audio_extractor_prefers_bbdown_and_falls_back_to_yt_dlp():
    calls: list[str] = []

    class FailingExtractor:
        def extract(self, *, source_url, referer, cookie_values, item_id):
            calls.append("bbdown")
            return AudioExtractionResult(ok=False, tool_name="BBDown", error_message="blocked")

    class PassingExtractor:
        def extract(self, *, source_url, referer, cookie_values, item_id):
            calls.append("yt-dlp")
            return AudioExtractionResult(
                ok=True,
                audio_path="E:/OneRadar/tmp/audio.m4a",
                mime_type="audio/mp4",
                tool_name="yt-dlp",
            )

    result = BilibiliAudioExtractor(
        extractors=(FailingExtractor(), PassingExtractor()),
    ).extract(
        source_url="https://www.bilibili.com/video/BV1test",
        referer="https://www.bilibili.com/video/BV1test",
        cookie_values={},
        item_id=uuid4(),
    )

    assert result.ok is True
    assert result.tool_name == "yt-dlp"
    assert calls == ["bbdown", "yt-dlp"]


def test_bbdown_uses_temporary_config_file_without_leaking_cookie_args(monkeypatch):
    observed: dict[str, object] = {}
    test_root = Path(".tmp-media-audio-tests") / str(uuid4())
    test_root.mkdir(parents=True, exist_ok=True)

    def fake_run(command, *, capture_output, check, text, encoding, errors, timeout, cwd, env):
        assert capture_output is True
        assert check is False
        assert text is True
        assert encoding == "utf-8"
        assert errors == "replace"
        assert timeout == 60
        assert env["DOTNET_ROLL_FORWARD"] == "Major"
        observed["command"] = command
        config_path = Path(command[command.index("--config-file") + 1])
        observed["config_path"] = config_path
        observed["config_text"] = config_path.read_text(encoding="utf-8")
        output_path = Path(cwd) / "audio.m4a"
        output_path.write_bytes(b"audio")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    item_id = uuid4()
    monkeypatch.setattr(subprocess, "run", fake_run)

    try:
        result = BbDownAudioExtractor(
            executable="BBDown",
            output_root=test_root,
            timeout_seconds=60,
        ).extract(
            source_url="https://www.bilibili.com/video/BV1test",
            referer="https://www.bilibili.com/video/BV1test",
            cookie_values={
                "sessdata": "secret-sessdata",
                "bili_jct": "secret-jct",
                "buvid3": "secret-buvid",
            },
            item_id=item_id,
        )

        command_text = " ".join(str(part) for part in observed["command"])
        assert result.ok is True
        assert "--config-file" in observed["command"]
        assert "secret-sessdata" not in command_text
        assert "secret-jct" not in command_text
        assert "secret-buvid" not in command_text
        assert "secret-sessdata" in str(observed["config_text"])
        assert not Path(observed["config_path"]).exists()
    finally:
        shutil.rmtree(test_root, ignore_errors=True)


def test_bilibili_legacy_audio_extractor_downloads_anonymous_dash_audio(monkeypatch):
    observed: dict[str, object] = {"urls": [], "headers": []}
    test_root = Path(".tmp-media-audio-tests") / str(uuid4())
    test_root.mkdir(parents=True, exist_ok=True)
    item_id = uuid4()

    class FakeResponse:
        def __init__(self, body: bytes):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return self.body

    def fake_urlopen(request, timeout):
        observed["urls"].append(request.full_url)
        observed["headers"].append(dict(request.header_items()))
        if "x/web-interface/view" in request.full_url:
            return FakeResponse(b'{"code":0,"data":{"cid":118176518}}')
        if "x/player/playurl" in request.full_url:
            return FakeResponse(
                b'{"code":0,"data":{"dash":{"audio":[{"id":30232,"bandwidth":132805,'
                b'"baseUrl":"https://upos.example/audio.m4s"}]}}}'
            )
        if request.full_url == "https://upos.example/audio.m4s":
            return FakeResponse(b"anonymous-m4s-audio")
        raise AssertionError(f"unexpected url: {request.full_url}")

    def fake_run(command, *, capture_output, check, text, encoding, errors, timeout):
        assert capture_output is True
        assert check is False
        assert text is True
        assert encoding == "utf-8"
        assert errors == "replace"
        assert timeout == 60
        observed["command"] = command
        output_path = Path(command[-1])
        output_path.write_bytes(b"audio")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("one_radar_worker.media_audio.urlopen", fake_urlopen)
    monkeypatch.setattr(subprocess, "run", fake_run)

    try:
        result = BilibiliLegacyAudioExtractor(
            ffmpeg_executable="ffmpeg",
            output_root=test_root,
            timeout_seconds=60,
        ).extract(
            source_url="https://www.bilibili.com/video/BV1UJ411g7oU/",
            referer="https://www.bilibili.com/video/BV1UJ411g7oU/",
            cookie_values={},
            item_id=item_id,
        )

        command = observed["command"]
        assert result.ok is True
        assert result.tool_name == "bilibili-legacy-playurl"
        assert result.mime_type == "audio/mp4"
        assert result.metadata["audio_id"] == 30232
        assert "--cookie" not in " ".join(str(part).lower() for part in command)
        assert all("Cookie" not in headers for headers in observed["headers"])
        assert any("x/player/playurl" in url for url in observed["urls"])
    finally:
        shutil.rmtree(test_root, ignore_errors=True)
