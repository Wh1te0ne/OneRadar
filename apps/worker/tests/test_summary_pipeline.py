from __future__ import annotations

from uuid import uuid4

from one_radar_worker.pipelines.common import PipelineContext
from one_radar_worker.pipelines.summary import SummaryPipeline, SummaryResult
from one_radar_worker.tasks import TaskType


def test_summary_pipeline_uses_provider_and_persists_short_summary():
    calls: list[tuple[dict[str, object], str, str]] = []

    class FakeAdapter:
        def summarize(self, *, provider_config, title, source_text):
            calls.append((provider_config, title, source_text))
            return SummaryResult(
                ok=True,
                content="这是一段由模型生成的摘要。",
                provider_name="Doubao",
                model_name="ep-test",
                error_message=None,
            )

    context = PipelineContext(
        item_id=uuid4(),
        source_url="https://example.com/article",
        task_type=TaskType.GENERATE_SUMMARY,
        payload={
            "title": "测试文章",
            "parsed_document": {
                "plain_text": "这是正文第一段。\n\n这是正文第二段。",
            },
            "summary_provider": {
                "provider_name": "Doubao",
                "base_url": "https://ark.example.com/api/v3",
                "api_key": "secret",
                "model_name": "ep-test",
            },
        },
    )

    result = SummaryPipeline(adapter=FakeAdapter()).run(context)

    assert result.ok is True
    assert calls == [
        (
            {**context.payload["summary_provider"], "content_type": ""},
            "测试文章",
            "这是正文第一段。\n\n这是正文第二段。",
        )
    ]
    summaries = result.data["persistable"]["summaries"]
    assert summaries == [
        {
            "summary_type": "short",
            "content": "这是一段由模型生成的摘要。",
            "provider_name": "Doubao",
            "model_name": "ep-test",
            "version": 1,
        }
    ]


def test_summary_pipeline_prefers_podcast_transcript_with_source_intro_context():
    calls: list[tuple[dict[str, object], str, str]] = []

    class FakeAdapter:
        def summarize(self, *, provider_config, title, source_text):
            calls.append((provider_config, title, source_text))
            return SummaryResult(
                ok=True,
                content="这是一段播客摘要。",
                provider_name="Doubao",
                model_name="ep-test",
                error_message=None,
            )

    context = PipelineContext(
        item_id=uuid4(),
        source_url="https://example.com/podcast/episode",
        task_type=TaskType.GENERATE_SUMMARY,
        payload={
            "title": "测试播客",
            "content_type": "podcast_episode",
            "parsed_document": {
                "plain_text": "这是 RSS 节目简介，不是完整内容。",
            },
            "transcript": {
                "full_text": "",
                "segments": [
                    {"start_ms": 12000, "end_ms": 18000, "text": "第一段真实转写。"},
                    {"start_ms": 66000, "end_ms": 72000, "text": "第二段真实转写。"},
                ],
            },
            "summary_provider": {
                "provider_name": "Doubao",
                "base_url": "https://ark.example.com/api/v3",
                "api_key": "secret",
                "model_name": "ep-test",
            },
        },
    )

    result = SummaryPipeline(adapter=FakeAdapter()).run(context)

    assert result.ok is True
    assert len(calls) == 1
    provider_config, title, source_text = calls[0]
    assert provider_config["content_type"] == "podcast_episode"
    assert title == "测试播客"
    assert "节目/来源简介" in source_text
    assert "这是 RSS 节目简介，不是完整内容。" in source_text
    assert "转写全文" in source_text
    assert "[00:12] 第一段真实转写。" in source_text
    assert "[01:06] 第二段真实转写。" in source_text
