from __future__ import annotations

import json
from uuid import uuid4

from one_radar_worker.pipelines import bilibili
from one_radar_worker.pipelines.bilibili import (
    BilibiliFetchResult,
    BilibiliPipeline,
    BilibiliTranscriptPayload,
    BilibiliVideoMetadata,
    BilibiliVideoRef,
)
from one_radar_worker.pipelines.common import PipelineContext, PipelineRunResult, PipelineStepResult
from one_radar_worker.processor import _pipeline_failure_message
from one_radar_worker.media_audio import AudioExtractionResult
from one_radar_worker.media_visual import (
    VisualFrameExtractionResult,
    VisualUnderstandingResult,
    VisualVideoExtractionResult,
)
from one_radar_worker.tasks import TaskType


def test_pipeline_failure_message_prefers_actionable_bilibili_step():
    result = PipelineRunResult(
        ok=False,
        steps=[
            PipelineStepResult("fetch_metadata", True, "Metadata fetched", {}),
            PipelineStepResult("extract_audio", True, "Audio extracted for ASR", {}),
            PipelineStepResult("transcribe_audio", False, "Transcription provider is not configured", {}),
            PipelineStepResult("build_transcript_view", False, "Metadata-only reader payload prepared", {}),
        ],
    )

    assert _pipeline_failure_message(result) == "Transcription provider is not configured"


def test_bilibili_pipeline_uses_asr_when_subtitles_are_unavailable(monkeypatch):
    video_ref = BilibiliVideoRef(
        source_url="https://www.bilibili.com/video/BV1test",
        normalized_url="https://www.bilibili.com/video/BV1test",
        bvid="BV1test",
        aid=None,
        page=1,
    )
    metadata = BilibiliVideoMetadata(
        bvid="BV1test",
        aid=123,
        cid=456,
        page=1,
        title="Test Video",
        description="",
        owner_name="Author",
        owner_id="42",
        cover_url=None,
        duration_seconds=12,
        published_at=None,
        part_title=None,
    )

    monkeypatch.setattr(bilibili, "_normalize_video_ref", lambda raw_url, cookie_values=None: video_ref)
    monkeypatch.setattr(
        bilibili,
        "_fetch_metadata",
        lambda video_ref, cookie_values=None: BilibiliFetchResult("fetch_metadata", True, "metadata-url", {"data": {}}),
    )
    monkeypatch.setattr(bilibili, "_extract_video_metadata", lambda video_ref, payload: metadata)
    monkeypatch.setattr(
        bilibili,
        "_fetch_subtitle_catalog",
        lambda video_ref, metadata, cookie_values=None: BilibiliFetchResult(
            "fetch_subtitles",
            True,
            "subtitle-url",
            {"data": {"subtitle": {"subtitles": []}}},
        ),
    )
    monkeypatch.setattr(bilibili, "_select_subtitle_track", lambda payload: None)

    class FakeAudioExtractor:
        def extract(self, *, source_url, referer, cookie_values, item_id):
            assert source_url == video_ref.normalized_url
            return AudioExtractionResult(
                ok=True,
                audio_path="E:/OneRadar/tmp/audio.m4a",
                mime_type="audio/mp4",
                tool_name="fake-yt-dlp",
                metadata={"size_bytes": 12},
            )

    class FakeTranscriptionAdapter:
        def transcribe(self, *, audio_path, mime_type, provider_config, language):
            assert audio_path.endswith("audio.m4a")
            assert provider_config["api_key"] == "sk-secret"
            assert provider_config["model_name"] == "asr-model"
            assert language == "zh-CN"
            return BilibiliTranscriptPayload(
                transcript_type="asr",
                language="zh-CN",
                full_text="First line\nSecond line",
                segments=[
                    {"start_ms": 0, "end_ms": 1000, "text": "First line", "speaker": None},
                    {"start_ms": 1000, "end_ms": 2000, "text": "Second line", "speaker": None},
                ],
                provider_name="OpenAI Compatible",
                model_name="asr-model",
                confidence_score=None,
            )

    context = PipelineContext(
        item_id=uuid4(),
        source_url=video_ref.source_url,
        task_type=TaskType.FETCH_META,
        payload={
            "transcription_provider": {
                "provider_name": "OpenAI Compatible",
                "provider_type": "openai_compatible",
                "base_url": "https://api.example.test/v1",
                "api_key": "sk-secret",
                "model_name": "asr-model",
            }
        },
    )

    result = BilibiliPipeline(
        audio_extractor=FakeAudioExtractor(),
        transcription_adapter=FakeTranscriptionAdapter(),
    ).run(context)

    assert result.ok is True
    assert [(step.step_name, step.ok) for step in result.steps if step.step_name in {"extract_audio", "transcribe_audio"}] == [
        ("extract_audio", True),
        ("transcribe_audio", True),
    ]

    persistable = result.data["persistable"]
    assert persistable["transcript"]["transcript_type"] == "asr"
    assert persistable["transcript"]["provider_name"] == "OpenAI Compatible"
    assert persistable["transcript"]["model_name"] == "asr-model"
    assert persistable["parsed_document"]["plain_text"] == "First line\nSecond line"
    assert persistable["content_item"]["raw_meta"]["transcript_status"] == "asr"
    assert "sk-secret" not in json.dumps(result.data, ensure_ascii=False)


def test_bilibili_pipeline_prefers_asr_even_when_subtitles_are_available(monkeypatch):
    video_ref = BilibiliVideoRef(
        source_url="https://www.bilibili.com/video/BV1subtitle",
        normalized_url="https://www.bilibili.com/video/BV1subtitle",
        bvid="BV1subtitle",
        aid=None,
        page=1,
    )
    metadata = BilibiliVideoMetadata(
        bvid="BV1subtitle",
        aid=123,
        cid=456,
        page=1,
        title="Subtitle Video",
        description="Only a short description",
        owner_name="Author",
        owner_id="42",
        cover_url=None,
        duration_seconds=60,
        published_at=None,
        part_title=None,
    )
    subtitle = BilibiliTranscriptPayload(
        transcript_type="subtitle",
        language="zh-CN",
        full_text="https://github.com/example\n欢迎 Star",
        segments=[
            {"start_ms": 0, "end_ms": 3000, "text": "https://github.com/example", "speaker": None},
            {"start_ms": 3000, "end_ms": 5000, "text": "欢迎 Star", "speaker": None},
        ],
    )

    monkeypatch.setattr(bilibili, "_normalize_video_ref", lambda raw_url, cookie_values=None: video_ref)
    monkeypatch.setattr(
        bilibili,
        "_fetch_metadata",
        lambda video_ref, cookie_values=None: BilibiliFetchResult("fetch_metadata", True, "metadata-url", {"data": {}}),
    )
    monkeypatch.setattr(bilibili, "_extract_video_metadata", lambda video_ref, payload: metadata)
    monkeypatch.setattr(
        bilibili,
        "_fetch_subtitle_catalog",
        lambda video_ref, metadata, cookie_values=None: BilibiliFetchResult(
            "fetch_subtitles",
            True,
            "subtitle-url",
            {"data": {"subtitle": {"subtitles": [{"subtitle_url": "https://example.test/sub.json", "lan": "zh-CN"}]}}},
        ),
    )
    monkeypatch.setattr(bilibili, "_fetch_subtitle_transcript", lambda track, referer, cookie_values=None: subtitle)

    class FakeAudioExtractor:
        def extract(self, *, source_url, referer, cookie_values, item_id):
            return AudioExtractionResult(
                ok=True,
                audio_path="E:/OneRadar/tmp/audio.m4a",
                mime_type="audio/mp4",
                tool_name="fake-yt-dlp",
                metadata={"size_bytes": 12},
            )

    class FakeTranscriptionAdapter:
        def transcribe(self, *, audio_path, mime_type, provider_config, language):
            return BilibiliTranscriptPayload(
                transcript_type="asr",
                language="zh-CN",
                full_text="这是来自音频转写的完整正文",
                segments=[
                    {"start_ms": 0, "end_ms": 3000, "text": "这是来自音频转写的完整正文", "speaker": None},
                ],
                provider_name="OpenAI Compatible",
                model_name="asr-model",
            )

    context = PipelineContext(
        item_id=uuid4(),
        source_url=video_ref.source_url,
        task_type=TaskType.FETCH_META,
        payload={
            "transcription_provider": {
                "provider_name": "OpenAI Compatible",
                "provider_type": "openai_compatible",
                "base_url": "https://api.example.test/v1",
                "api_key": "sk-secret",
                "model_name": "asr-model",
            }
        },
    )

    result = BilibiliPipeline(
        audio_extractor=FakeAudioExtractor(),
        transcription_adapter=FakeTranscriptionAdapter(),
    ).run(context)

    assert result.ok is True
    persistable = result.data["persistable"]
    assert persistable["transcript"]["transcript_type"] == "asr"
    assert persistable["parsed_document"]["plain_text"] == "这是来自音频转写的完整正文"
    assert "github.com/example" not in persistable["parsed_document"]["plain_text"]


def test_bilibili_pipeline_runs_visual_enhancement_after_asr(monkeypatch):
    video_ref = BilibiliVideoRef(
        source_url="https://www.bilibili.com/video/BV1visual",
        normalized_url="https://www.bilibili.com/video/BV1visual",
        bvid="BV1visual",
        aid=None,
        page=1,
    )
    metadata = BilibiliVideoMetadata(
        bvid="BV1visual",
        aid=123,
        cid=456,
        page=1,
        title="Visual Video",
        description="A video with slides",
        owner_name="Author",
        owner_id="42",
        cover_url=None,
        duration_seconds=60,
        published_at=None,
        part_title=None,
    )
    subtitle = BilibiliTranscriptPayload(
        transcript_type="subtitle",
        language="zh-CN",
        full_text="这里讲到了架构图。",
        segments=[
            {"start_ms": 0, "end_ms": 3000, "text": "这里讲到了架构图。", "speaker": None},
        ],
    )

    monkeypatch.setattr(bilibili, "_normalize_video_ref", lambda raw_url, cookie_values=None: video_ref)
    monkeypatch.setattr(
        bilibili,
        "_fetch_metadata",
        lambda video_ref, cookie_values=None: BilibiliFetchResult("fetch_metadata", True, "metadata-url", {"data": {}}),
    )
    monkeypatch.setattr(bilibili, "_extract_video_metadata", lambda video_ref, payload: metadata)
    monkeypatch.setattr(
        bilibili,
        "_fetch_subtitle_catalog",
        lambda video_ref, metadata, cookie_values=None: BilibiliFetchResult(
            "fetch_subtitles",
            True,
            "subtitle-url",
            {"data": {"subtitle": {"subtitles": [{"subtitle_url": "https://example.test/sub.json", "lan": "zh-CN"}]}}},
        ),
    )
    monkeypatch.setattr(bilibili, "_fetch_subtitle_transcript", lambda track, referer, cookie_values=None: subtitle)

    class FakeAudioExtractor:
        def extract(self, *, source_url, referer, cookie_values, item_id):
            return AudioExtractionResult(ok=True, audio_path="audio.m4a", mime_type="audio/mp4", tool_name="fake", metadata={})

    class FakeTranscriptionAdapter:
        def transcribe(self, *, audio_path, mime_type, provider_config, language):
            return BilibiliTranscriptPayload(
                transcript_type="asr",
                language="zh-CN",
                full_text="这里讲到了架构图。",
                segments=[{"start_ms": 0, "end_ms": 3000, "text": "这里讲到了架构图。", "speaker": None}],
                provider_name="OpenAI Compatible",
                model_name="asr-model",
            )

    class FakeFrameExtractor:
        def extract_frames(self, *, source_url, referer, cookie_values, item_id, duration_seconds):
            assert source_url == video_ref.normalized_url
            assert duration_seconds == 60
            return VisualFrameExtractionResult(ok=True, frame_paths=["frame-001.jpg", "frame-002.jpg"], metadata={"frame_count": 2})

    class FakeVideoExtractor:
        def extract_clip(self, *, source_url, referer, cookie_values, item_id, duration_seconds):
            return VisualVideoExtractionResult(ok=False, error_message="direct video unavailable")

    class FakeVisualAdapter:
        def analyze(self, *, frame_paths, provider_config, video_metadata, transcript_text, language):
            assert frame_paths == ["frame-001.jpg", "frame-002.jpg"]
            assert provider_config["api_key"] == "sk-visual-secret"
            assert provider_config["model_name"] == "vision-model"
            assert video_metadata["title"] == "Visual Video"
            assert "架构图" in transcript_text
            assert language == "zh-CN"
            return VisualUnderstandingResult(
                ok=True,
                summary="画面展示了一张系统架构图，包含 API、Worker 和数据库。",
                provider_name="OpenAI Compatible",
                model_name="vision-model",
                metadata={"frame_count": 2},
            )

    context = PipelineContext(
        item_id=uuid4(),
        source_url=video_ref.source_url,
        task_type=TaskType.FETCH_META,
        payload={
            "visual_enhancement": {"enabled": True},
            "transcription_provider": {
                "provider_name": "OpenAI Compatible",
                "provider_type": "openai_compatible",
                "base_url": "https://api.example.test/v1",
                "api_key": "sk-secret",
                "model_name": "asr-model",
            },
            "visual_understanding_provider": {
                "provider_name": "OpenAI Compatible",
                "provider_type": "openai_compatible",
                "base_url": "https://api.example.test/v1",
                "api_key": "sk-visual-secret",
                "model_name": "vision-model",
            },
        },
    )

    result = BilibiliPipeline(
        audio_extractor=FakeAudioExtractor(),
        transcription_adapter=FakeTranscriptionAdapter(),
        visual_video_extractor=FakeVideoExtractor(),
        visual_frame_extractor=FakeFrameExtractor(),
        visual_understanding_adapter=FakeVisualAdapter(),
    ).run(context)

    assert result.ok is True
    assert [
        (step.step_name, step.ok)
        for step in result.steps
        if step.step_name in {"extract_visual_video", "extract_visual_frames", "analyze_visual_context"}
    ] == [
        ("extract_visual_video", False),
        ("extract_visual_frames", True),
        ("analyze_visual_context", True),
    ]
    summaries = result.data["persistable"]["summaries"]
    assert summaries[0]["summary_type"] == "visual_context"
    assert "系统架构图" in summaries[0]["content"]
    assert result.data["persistable"]["content_item"]["raw_meta"]["visual_enhancement_status"] == "completed"
    assert "sk-visual-secret" not in json.dumps(result.data, ensure_ascii=False)


def test_bilibili_pipeline_prefers_direct_video_visual_enhancement(monkeypatch):
    video_ref = BilibiliVideoRef(
        source_url="https://www.bilibili.com/video/BV1direct",
        normalized_url="https://www.bilibili.com/video/BV1direct",
        bvid="BV1direct",
        aid=None,
        page=1,
    )
    metadata = BilibiliVideoMetadata(
        bvid="BV1direct",
        aid=123,
        cid=456,
        page=1,
        title="Direct Visual Video",
        description="A video with a demo",
        owner_name="Author",
        owner_id="42",
        cover_url=None,
        duration_seconds=60,
        published_at=None,
        part_title=None,
    )
    subtitle = BilibiliTranscriptPayload(
        transcript_type="subtitle",
        language="zh-CN",
        full_text="这里展示了一个操作演示。",
        segments=[
            {"start_ms": 0, "end_ms": 3000, "text": "这里展示了一个操作演示。", "speaker": None},
        ],
    )

    monkeypatch.setattr(bilibili, "_normalize_video_ref", lambda raw_url, cookie_values=None: video_ref)
    monkeypatch.setattr(
        bilibili,
        "_fetch_metadata",
        lambda video_ref, cookie_values=None: BilibiliFetchResult("fetch_metadata", True, "metadata-url", {"data": {}}),
    )
    monkeypatch.setattr(bilibili, "_extract_video_metadata", lambda video_ref, payload: metadata)
    monkeypatch.setattr(
        bilibili,
        "_fetch_subtitle_catalog",
        lambda video_ref, metadata, cookie_values=None: BilibiliFetchResult(
            "fetch_subtitles",
            True,
            "subtitle-url",
            {"data": {"subtitle": {"subtitles": [{"subtitle_url": "https://example.test/sub.json", "lan": "zh-CN"}]}}},
        ),
    )
    monkeypatch.setattr(bilibili, "_fetch_subtitle_transcript", lambda track, referer, cookie_values=None: subtitle)

    class FakeAudioExtractor:
        def extract(self, *, source_url, referer, cookie_values, item_id):
            return AudioExtractionResult(ok=True, audio_path="audio.m4a", mime_type="audio/mp4", tool_name="fake", metadata={})

    class FakeTranscriptionAdapter:
        def transcribe(self, *, audio_path, mime_type, provider_config, language):
            return BilibiliTranscriptPayload(
                transcript_type="asr",
                language="zh-CN",
                full_text="这里展示了一个操作演示。",
                segments=[{"start_ms": 0, "end_ms": 3000, "text": "这里展示了一个操作演示。", "speaker": None}],
                provider_name="OpenAI Compatible",
                model_name="asr-model",
            )

    class FakeVideoExtractor:
        def extract_clip(self, *, source_url, referer, cookie_values, item_id, duration_seconds):
            assert source_url == video_ref.normalized_url
            assert duration_seconds == 60
            return VisualVideoExtractionResult(
                ok=True,
                video_path="visual_clip.mp4",
                mime_type="video/mp4",
                metadata={"size_bytes": 2048},
            )

    class FailingFrameExtractor:
        def extract_frames(self, *, source_url, referer, cookie_values, item_id, duration_seconds):
            raise AssertionError("frame fallback should not run after successful direct video analysis")

    class FakeVisualAdapter:
        def analyze_video(self, *, video_path, provider_config, video_metadata, transcript_text, language):
            assert video_path == "visual_clip.mp4"
            assert provider_config["model_name"] == "vision-model"
            assert video_metadata["title"] == "Direct Visual Video"
            assert "操作演示" in transcript_text
            assert language == "zh-CN"
            return VisualUnderstandingResult(
                ok=True,
                summary="视频片段展示了一个屏幕操作演示。",
                provider_name="OpenAI Compatible",
                model_name="vision-model",
                metadata={"video_size_bytes": 2048},
            )

        def analyze(self, *, frame_paths, provider_config, video_metadata, transcript_text, language):
            raise AssertionError("frame analysis should not run after successful direct video analysis")

    context = PipelineContext(
        item_id=uuid4(),
        source_url=video_ref.source_url,
        task_type=TaskType.FETCH_META,
        payload={
            "visual_enhancement": {"enabled": True},
            "transcription_provider": {
                "provider_name": "OpenAI Compatible",
                "provider_type": "openai_compatible",
                "base_url": "https://api.example.test/v1",
                "api_key": "sk-secret",
                "model_name": "asr-model",
            },
            "visual_understanding_provider": {
                "provider_name": "OpenAI Compatible",
                "provider_type": "openai_compatible",
                "base_url": "https://api.example.test/v1",
                "api_key": "sk-visual-secret",
                "model_name": "vision-model",
            },
        },
    )

    result = BilibiliPipeline(
        audio_extractor=FakeAudioExtractor(),
        transcription_adapter=FakeTranscriptionAdapter(),
        visual_video_extractor=FakeVideoExtractor(),
        visual_frame_extractor=FailingFrameExtractor(),
        visual_understanding_adapter=FakeVisualAdapter(),
    ).run(context)

    assert result.ok is True
    assert [
        (step.step_name, step.ok)
        for step in result.steps
        if step.step_name in {"extract_visual_video", "analyze_visual_video", "extract_visual_frames"}
    ] == [
        ("extract_visual_video", True),
        ("analyze_visual_video", True),
    ]
    summary = result.data["persistable"]["summaries"][0]
    assert summary["summary_type"] == "visual_context"
    assert summary["evidence"][0]["type"] == "sampled_video_clip"
    assert summary["evidence"][0]["video_size_bytes"] == 2048
    raw_meta = result.data["persistable"]["content_item"]["raw_meta"]
    assert raw_meta["visual_enhancement"]["source_type"] == "sampled_video_clip"
    assert "sk-visual-secret" not in json.dumps(result.data, ensure_ascii=False)
