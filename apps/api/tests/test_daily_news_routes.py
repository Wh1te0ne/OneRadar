from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.feeds import FeedPreviewItem, FeedPreviewResponse, FeedStateResponse
from app.services import daily_news_service


def _feed_state() -> FeedStateResponse:
    return FeedStateResponse(
        sources=[],
        feeds={
            "https://example.com/rss.xml": FeedPreviewResponse(
                source_url="https://example.com/rss.xml",
                site_title="Example Feed",
                site_url="https://example.com",
                description=None,
                fetched_at=datetime(2026, 5, 7, 1, 0, tzinfo=timezone.utc),
                items=[
                    FeedPreviewItem(
                        id="entry-0",
                        title="Previous day infrastructure funding",
                        link="https://example.com/infra-funding",
                        summary="A funding story from the rolling freshness window.",
                        author="Reporter",
                        published_at=datetime(2026, 5, 6, 9, 0, tzinfo=timezone.utc),
                        tags=["AI"],
                    ),
                    FeedPreviewItem(
                        id="entry-1",
                        title="OpenAI releases a new model",
                        link="https://example.com/openai-model",
                        summary="A new model improves coding and reasoning.",
                        author="Reporter",
                        published_at=datetime(2026, 5, 7, 0, 30, tzinfo=timezone.utc),
                        tags=["AI"],
                    ),
                    FeedPreviewItem(
                        id="entry-old",
                        title="Old model news",
                        link="https://example.com/old-model",
                        summary="This is outside the 24 hour freshness window.",
                        author="Reporter",
                        published_at=datetime(2026, 5, 6, 7, 30, tzinfo=timezone.utc),
                        tags=["AI"],
                    )
                ],
            )
        },
        read_entries=[],
    )


def test_generate_daily_news_persists_one_report_per_date(client, monkeypatch) -> None:
    monkeypatch.setattr(daily_news_service, "get_feed_state", _feed_state)
    monkeypatch.setattr(
        daily_news_service,
        "_daily_news_reference_time",
        lambda: datetime(2026, 5, 7, 8, 0, tzinfo=timezone.utc),
    )

    def fake_generate(entries, report_date):
        assert report_date == "2026-05-07"
        assert entries[0]["original_id"] == "entry-1"
        assert any(entry["original_id"] == "entry-0" for entry in entries)
        assert all(entry["original_id"] != "entry-old" for entry in entries)
        return {
            "headline": "今日 AI 新闻",
            "lead": {
                "title": "OpenAI 发布新模型",
                "summary": "新模型提升代码与推理能力。",
                "entry_id": entries[0]["id"],
            },
            "sections": [
                {
                    "title": "大模型技术进展",
                    "summary": "模型能力继续快速迭代。",
                    "items": [
                            {
                                "title": "OpenAI 发布新模型",
                                "summary": "代码与推理能力增强。",
                                "entry_id": entries[0]["id"],
                            }
                    ],
                }
            ],
            "provider_name": "TestProvider",
            "model_name": "test-model",
        }

    monkeypatch.setattr(daily_news_service, "_generate_report_payload", fake_generate)

    response = client.post("/api/daily-news/generate", json={"date": "2026-05-07", "force": True})

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["report_date"] == "2026-05-07"
    assert body["status"] == "ready"
    assert body["headline"] == "今日 AI 新闻"
    assert body["lead"]["entry"]["source_title"] == "Example Feed"
    assert body["sections"][0]["items"][0]["entry"]["link"] == "https://example.com/openai-model"

    second = client.get("/api/daily-news", params={"date": "2026-05-07"})
    assert second.status_code == 200
    assert second.json()["headline"] == "今日 AI 新闻"


def test_generate_daily_news_requires_force_when_report_exists(client, monkeypatch) -> None:
    monkeypatch.setattr(daily_news_service, "get_feed_state", _feed_state)
    monkeypatch.setattr(
        daily_news_service,
        "_generate_report_payload",
        lambda entries, report_date: {
            "headline": "第一次日报",
            "lead": {"title": "标题", "summary": "摘要", "entry_id": "n1"},
            "sections": [],
            "provider_name": "TestProvider",
            "model_name": "test-model",
        },
    )

    create_response = client.post(
        "/api/daily-news/generate",
        json={"date": "2026-05-07", "force": True},
    )
    assert create_response.status_code == 200

    response = client.post("/api/daily-news/generate", json={"date": "2026-05-07"})

    assert response.status_code == 409
    assert "已存在" in response.json()["detail"]


def test_get_daily_news_missing_date_returns_missing_status(client) -> None:
    response = client.get("/api/daily-news", params={"date": "2026-05-06"})

    assert response.status_code == 200
    assert response.json()["report_date"] == "2026-05-06"
    assert response.json()["status"] == "missing"


def test_daily_news_prompt_requires_ai_first_and_games_last() -> None:
    entries = [
        {
            "id": "n1",
            "source_title": "Example Feed",
            "published_at": datetime(2026, 5, 7, 0, 30, tzinfo=timezone.utc),
            "title": "AI model update",
            "summary": "A new AI model ships.",
            "tags": ["AI"],
        }
    ]

    prompt = daily_news_service._daily_news_prompt(entries, "2026-05-07")

    assert "lead 和 headline 必须优先选择 AI 新闻" in prompt
    assert "第一个主题必须是 AI 相关新闻" in prompt
    assert "AI 相关新闻的篇幅和条目数量应明显多于其他主题" in prompt
    assert "游戏新闻只能放在最后一个主题" in prompt
