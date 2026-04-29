from fastapi import APIRouter, HTTPException

from app.schemas.podcasts import (
    PodcastEpisodeFeedResponse,
    PodcastEpisodeImportRequest,
    PodcastEpisodeImportResponse,
    PodcastSearchResponse,
    PodcastSubscriptionCreateRequest,
    PodcastSubscriptionDeleteResponse,
    PodcastSubscriptionEntry,
    PodcastSubscriptionListResponse,
)
from app.services import podcast_service

router = APIRouter(prefix="/podcasts", tags=["podcasts"])


@router.get("/search")
def search_podcasts(q: str, country: str = "US", limit: int = 12) -> PodcastSearchResponse:
    try:
        return podcast_service.search_podcasts(q, country=country, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/subscriptions")
def list_subscriptions() -> PodcastSubscriptionListResponse:
    return podcast_service.list_subscriptions()


@router.post("/subscriptions")
def create_subscription(payload: PodcastSubscriptionCreateRequest) -> PodcastSubscriptionEntry:
    try:
        return podcast_service.create_subscription(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/subscriptions/{subscription_id}")
def delete_subscription(subscription_id: str) -> PodcastSubscriptionDeleteResponse:
    return podcast_service.delete_subscription(subscription_id)


@router.get("/episodes")
def list_subscription_episodes(limit: int = 80) -> PodcastEpisodeFeedResponse:
    return PodcastEpisodeFeedResponse(
        items=podcast_service.list_subscription_episodes(limit=limit)
    )


@router.get("/feed-episodes")
def preview_feed_episodes(
    feed_url: str,
    title: str | None = None,
    author: str | None = None,
    image_url: str | None = None,
    limit: int = 80,
) -> PodcastEpisodeFeedResponse:
    try:
        return PodcastEpisodeFeedResponse(
            items=podcast_service.preview_feed_episodes(
                feed_url=feed_url,
                title=title,
                author=author,
                image_url=image_url,
                limit=limit,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/episodes/import")
def import_episode(payload: PodcastEpisodeImportRequest) -> PodcastEpisodeImportResponse:
    try:
        return podcast_service.import_episode(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
