from fastapi import APIRouter, HTTPException

from app.schemas.feeds import FeedPreviewResponse
from app.services.feed_service import preview_feed as preview_feed_service

router = APIRouter(prefix="/feeds", tags=["feeds"])


@router.get("/preview")
def preview_feed(url: str, limit: int = 12) -> FeedPreviewResponse:
    try:
        return preview_feed_service(url, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
