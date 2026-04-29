from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError

from app.services import podcast_service


def test_podcast_search_uses_apple_results(client, monkeypatch) -> None:
    def fake_search(query: str, country: str, limit: int):
        assert query == "凹凸电波"
        assert country == "US"
        assert limit == 8
        return [
            {
                "collectionId": 1455784513,
                "collectionName": "凹凸电波",
                "artistName": "凹凸电波",
                "feedUrl": "http://www.ximalaya.com/album/19206382.xml",
                "artworkUrl600": "https://example.com/cover.jpg",
                "primaryGenreName": "Comedy",
                "trackCount": 369,
            }
        ]

    monkeypatch.setattr(podcast_service, "_search_apple_podcasts", fake_search)

    response = client.get(
        "/api/podcasts/search",
        params={"q": "凹凸电波", "country": "US", "limit": 8},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["itunes_id"] == "1455784513"
    assert body["items"][0]["title"] == "凹凸电波"
    assert body["items"][0]["feed_url"] == "http://www.ximalaya.com/album/19206382.xml"
    assert body["items"][0]["is_subscribable"] is True


def test_podcast_subscriptions_are_server_side(client, monkeypatch) -> None:
    def failing_session_local():
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(podcast_service, "SessionLocal", failing_session_local)

    create_response = client.post(
        "/api/podcasts/subscriptions",
        json={
            "feed_url": "http://www.ximalaya.com/album/19206382.xml",
            "title": "凹凸电波",
            "author": "凹凸电波",
            "image_url": "https://example.com/cover.jpg",
            "itunes_id": "1455784513",
        },
    )

    assert create_response.status_code == 200
    subscription = create_response.json()
    assert subscription["title"] == "凹凸电波"
    assert subscription["feed_url"] == "http://www.ximalaya.com/album/19206382.xml"

    list_response = client.get("/api/podcasts/subscriptions")
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["id"] == subscription["id"]

    delete_response = client.delete(f"/api/podcasts/subscriptions/{subscription['id']}")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True
    assert client.get("/api/podcasts/subscriptions").json()["items"] == []


def test_podcast_episode_feed_includes_enclosures(client, monkeypatch) -> None:
    def fake_preview_subscriptions(limit: int):
        assert limit == 20
        return [
            podcast_service.PodcastEpisodeFeedEntry(
                id="feed-1:episode-guid",
                subscription_id="feed-1",
                feed_url="https://example.com/podcast.xml",
                podcast_title="凹凸电波",
                title="最新一期",
                guid="episode-guid",
                link="https://example.com/episodes/1",
                summary="episode summary",
                author="主播",
                published_at=datetime(2026, 4, 27, 12, tzinfo=UTC),
                duration_seconds=3600,
                enclosure_url="https://cdn.example.com/audio.m4a",
                enclosure_type="audio/x-m4a",
                enclosure_length=12345,
                image_url="https://example.com/cover.jpg",
                is_imported=False,
                item_id=None,
            )
        ]

    monkeypatch.setattr(
        podcast_service,
        "list_subscription_episodes",
        fake_preview_subscriptions,
    )

    response = client.get("/api/podcasts/episodes", params={"limit": 20})

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["podcast_title"] == "凹凸电波"
    assert body["items"][0]["enclosure_url"] == "https://cdn.example.com/audio.m4a"
    assert body["items"][0]["is_imported"] is False


def test_podcast_feed_episode_preview_uses_feed_url(client, monkeypatch) -> None:
    def fake_preview_feed_episodes(
        feed_url: str,
        title: str | None,
        author: str | None,
        image_url: str | None,
        limit: int,
    ):
        assert feed_url == "https://example.com/podcast.xml"
        assert title == "凹凸电波"
        assert author == "主播"
        assert image_url == "https://example.com/cover.jpg"
        assert limit == 30
        return [
            podcast_service.PodcastEpisodeFeedEntry(
                id="feed-preview:episode-guid",
                subscription_id=None,
                feed_url="https://example.com/podcast.xml",
                podcast_title="凹凸电波",
                title="预览单集",
                guid="episode-guid",
                link="https://example.com/episodes/preview",
                summary="preview summary",
                author="主播",
                published_at=datetime(2026, 4, 28, 9, tzinfo=UTC),
                duration_seconds=1800,
                enclosure_url="https://cdn.example.com/audio.mp3",
                enclosure_type="audio/mpeg",
                enclosure_length=45678,
                image_url="https://example.com/cover.jpg",
                is_imported=False,
                item_id=None,
            )
        ]

    monkeypatch.setattr(
        podcast_service,
        "preview_feed_episodes",
        fake_preview_feed_episodes,
    )

    response = client.get(
        "/api/podcasts/feed-episodes",
        params={
            "feed_url": "https://example.com/podcast.xml",
            "title": "凹凸电波",
            "author": "主播",
            "image_url": "https://example.com/cover.jpg",
            "limit": 30,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["podcast_title"] == "凹凸电波"
    assert body["items"][0]["subscription_id"] is None
    assert body["items"][0]["enclosure_url"] == "https://cdn.example.com/audio.mp3"


def test_import_podcast_episode_deduplicates_by_episode_identity(client, monkeypatch) -> None:
    def failing_session_local():
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(podcast_service, "SessionLocal", failing_session_local)

    payload = {
        "feed_url": "https://example.com/podcast.xml",
        "podcast_title": "凹凸电波",
        "title": "最新一期",
        "guid": "episode-guid",
        "link": "https://example.com/episodes/1",
        "published_at": "2026-04-27T12:00:00Z",
        "enclosure_url": "https://cdn.example.com/audio.m4a",
        "enclosure_type": "audio/x-m4a",
        "enclosure_length": 12345,
    }

    first_response = client.post("/api/podcasts/episodes/import", json=payload)
    duplicate_response = client.post("/api/podcasts/episodes/import", json=payload)

    assert first_response.status_code == 200
    first_body = first_response.json()
    assert first_body["content_type"] == "podcast_episode"
    assert first_body["is_duplicate"] is False
    assert first_body["task_id"]

    assert duplicate_response.status_code == 200
    duplicate_body = duplicate_response.json()
    assert duplicate_body["is_duplicate"] is True
    assert duplicate_body["item_id"] == first_body["item_id"]
    assert duplicate_body["task_id"] is None
