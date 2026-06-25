from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from app.services import analysis_service


def _stub_platform_preview(url: str, platform: str):
    return SimpleNamespace(
        final_url=url,
        platform=platform,
        content_type="video" if platform == "douyin" else "note",
        title="平台内容标题",
        source_name="抖音" if platform == "douyin" else "小红书",
        author="测试作者",
        published_at=None,
        original_text="平台内容标题\n测试作者\n这是一段平台可见正文。",
        source_text_kind="platform_visible_text",
        metadata={
            "parser_name": "parsehub",
            "media_count": 1,
            "media": [{"url": "https://example.com/media.mp4"}],
        },
        fetched_at=datetime.now(UTC),
    )


def test_analyze_web_url_returns_full_source_material(client, monkeypatch):
    monkeypatch.setattr(
        analysis_service,
        "preview_feed_article",
        lambda url: SimpleNamespace(
            final_url=url,
            title="网页文章标题",
            site_title="Example",
            author="作者",
            published_at=None,
            plain_text="这是完整的网页正文。\n第二段内容。",
            summary="网页摘要",
            parser_name="readability",
            parser_version="test",
            fetched_at=datetime.now(UTC),
        ),
    )
    monkeypatch.setattr(
        analysis_service,
        "_model_summary",
        lambda title, source_text: ("网页总结", "extractive", None),
    )

    response = client.post("/api/analysis/url", json={"url": "https://example.com/article"})

    assert response.status_code == 200
    body = response.json()
    assert body["platform"] == "web"
    assert body["content_type"] == "article"
    assert body["source_material"]["kind"] == "article_text"
    assert body["source_material"]["completeness"] == "full"
    assert body["source_material"]["warnings"] == []
    assert body["source_material"]["text"] == "这是完整的网页正文。\n第二段内容。"
    assert body["summary_markdown"].startswith("## AI 总结")


def test_analyze_douyin_url_uses_social_platform_adapter(client, monkeypatch):
    monkeypatch.setattr(
        analysis_service,
        "preview_social_platform_url",
        _stub_platform_preview,
        raising=False,
    )
    monkeypatch.setattr(
        analysis_service,
        "_model_summary",
        lambda title, source_text: ("测试摘要", "extractive", None),
    )

    response = client.post("/api/analysis/url", json={"url": "https://v.douyin.com/iabc123/"})

    assert response.status_code == 200
    body = response.json()
    assert body["platform"] == "douyin"
    assert body["content_type"] == "video"
    assert body["source_text_kind"] == "platform_visible_text"
    assert body["original_text"].startswith("平台内容标题")
    assert body["metadata"]["parser_name"] == "parsehub"
    assert body["persisted"] is False
    assert body["source_material"]["kind"] == "caption_plus_media"
    assert body["source_material"]["text"].startswith("平台内容标题")
    assert body["source_material"]["markdown"].startswith("# 平台内容标题")
    assert body["source_material"]["completeness"] == "partial"
    assert body["source_material"]["warnings"]
    assert body["source_material"]["assets"] == [{"index": 1, "metadata": {"url": "https://example.com/media.mp4"}}]
    assert body["ai_summary"]["summary"] == "测试摘要"
    assert body["ai_summary"]["markdown"].startswith("## AI 总结")
    assert body["summary_markdown"] == body["ai_summary"]["markdown"]
    assert body["source_markdown"] == body["source_material"]["markdown"]


def test_analyze_xiaohongshu_url_uses_social_platform_adapter(client, monkeypatch):
    monkeypatch.setattr(
        analysis_service,
        "preview_social_platform_url",
        _stub_platform_preview,
        raising=False,
    )
    monkeypatch.setattr(
        analysis_service,
        "_model_summary",
        lambda title, source_text: ("测试摘要", "extractive", None),
    )

    response = client.post("/api/analysis/url", json={"url": "https://xhslink.com/a/abc123"})

    assert response.status_code == 200
    body = response.json()
    assert body["platform"] == "xiaohongshu"
    assert body["content_type"] == "note"
    assert body["source_name"] == "小红书"
    assert body["source_text_kind"] == "platform_visible_text"
    assert body["persisted"] is False
    assert body["source_material"]["kind"] == "caption_plus_media"
    assert body["source_material"]["completeness"] == "partial"
    assert body["ai_summary"]["provider"] == "extractive"
