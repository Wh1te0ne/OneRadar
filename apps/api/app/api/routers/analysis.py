from fastapi import APIRouter, HTTPException

from app.schemas.analysis import UrlAnalysisRequest, UrlAnalysisResponse
from app.services.analysis_service import analyze_url as analyze_url_service

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("/url")
def analyze_url(payload: UrlAnalysisRequest) -> UrlAnalysisResponse:
    try:
        return analyze_url_service(payload.url, payload.platform_hint)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
