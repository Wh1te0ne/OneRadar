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
        metadata={"parser_name": "parsehub", "media_count": 1},
        fetched_at=datetime.now(UTC),
    )


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
