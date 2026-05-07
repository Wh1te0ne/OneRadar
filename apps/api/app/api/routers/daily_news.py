from fastapi import APIRouter

from app.schemas.daily_news import DailyNewsGenerateRequest, DailyNewsReportResponse
from app.services.daily_news_service import generate_daily_news as generate_daily_news_service
from app.services.daily_news_service import get_daily_news as get_daily_news_service

router = APIRouter(prefix="/daily-news", tags=["daily-news"])


@router.get("")
def get_daily_news(date: str | None = None) -> DailyNewsReportResponse:
    return get_daily_news_service(date)


@router.post("/generate")
def generate_daily_news(payload: DailyNewsGenerateRequest) -> DailyNewsReportResponse:
    return generate_daily_news_service(payload)
