from fastapi import APIRouter

from app.schemas.daily_news import DailyNewsGenerateRequest, DailyNewsReportResponse, DailyNewsShareRequest, DailyNewsShareResponse
from app.services.daily_news_service import create_daily_news_share as create_daily_news_share_service
from app.services.daily_news_service import generate_daily_news as generate_daily_news_service
from app.services.daily_news_service import get_daily_news as get_daily_news_service
from app.services.daily_news_service import get_public_daily_news_by_share_id
from app.services.daily_news_service import get_public_daily_news_by_user_share_key

router = APIRouter(prefix="/daily-news", tags=["daily-news"])
public_router = APIRouter(prefix="/public/daily-news", tags=["daily-news"])


@router.get("")
def get_daily_news(date: str | None = None) -> DailyNewsReportResponse:
    return get_daily_news_service(date)


@router.post("/generate")
def generate_daily_news(payload: DailyNewsGenerateRequest) -> DailyNewsReportResponse:
    return generate_daily_news_service(payload)


@router.post("/share")
def create_daily_news_share(payload: DailyNewsShareRequest) -> DailyNewsShareResponse:
    return create_daily_news_share_service(payload)


@public_router.get("/shares/{share_id}")
def get_public_daily_news(share_id: str) -> DailyNewsReportResponse:
    return get_public_daily_news_by_share_id(share_id)


@public_router.get("/users/{share_key}/{date}")
def get_public_daily_news_by_user_key(share_key: str, date: str) -> DailyNewsReportResponse:
    return get_public_daily_news_by_user_share_key(share_key, date)
