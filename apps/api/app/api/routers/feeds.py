from fastapi import APIRouter, HTTPException

from app.schemas.feeds import (
    FeedArticlePreviewResponse,
    FeedCacheRequest,
    FeedDeleteSourceResponse,
    FeedPreviewResponse,
    FeedReadRequest,
    FeedRefreshResponse,
    FeedSourceErrorRequest,
    FeedStateResponse,
)
from app.services.feed_refresh_service import refresh_all_feeds as refresh_all_feeds_service
from app.services.feed_state_service import delete_feed_source as delete_feed_source_service
from app.services.feed_state_service import get_feed_state as get_feed_state_service
from app.services.feed_state_service import mark_feed_source_error as mark_feed_source_error_service
from app.services.feed_state_service import mark_feed_entry_read as mark_feed_entry_read_service
from app.services.feed_state_service import upsert_feed_cache as upsert_feed_cache_service
from app.services.feed_service import preview_feed as preview_feed_service
from app.services.feed_service import preview_feed_article as preview_feed_article_service

router = APIRouter(prefix="/feeds", tags=["feeds"])


@router.get("/preview")
def preview_feed(url: str, limit: int = 12) -> FeedPreviewResponse:
    try:
        return preview_feed_service(url, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/state")
def get_feed_state() -> FeedStateResponse:
    return get_feed_state_service()


@router.post("/cache")
def upsert_feed_cache(payload: FeedCacheRequest) -> FeedStateResponse:
    return upsert_feed_cache_service(payload.feed)


@router.post("/read")
def mark_feed_entry_read(payload: FeedReadRequest) -> FeedStateResponse:
    return mark_feed_entry_read_service(payload.entry_key)


@router.post("/sources/error")
def mark_feed_source_error(payload: FeedSourceErrorRequest) -> FeedStateResponse:
    return mark_feed_source_error_service(payload.source_url, payload.site_title, payload.error_message)


@router.post("/refresh")
def refresh_feeds() -> FeedRefreshResponse:
    return refresh_all_feeds_service()


@router.delete("/sources")
def delete_feed_source(url: str) -> FeedDeleteSourceResponse:
    return FeedDeleteSourceResponse(source_url=url, deleted=delete_feed_source_service(url))


@router.get("/article-preview")
def preview_feed_article(
    url: str,
    title: str | None = None,
    source_title: str | None = None,
    author: str | None = None,
    published_at: str | None = None,
    summary: str | None = None,
) -> FeedArticlePreviewResponse:
    try:
        return preview_feed_article_service(
            url,
            title=title,
            source_title=source_title,
            author=author,
            published_at=published_at,
            summary=summary,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
