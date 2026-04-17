from fastapi import APIRouter

from app.schemas.settings import BilibiliIntegrationCookieParseResponse, BilibiliIntegrationSettingsEntry, BilibiliIntegrationSettingsUpdateRequest
from app.services.settings_service import get_bilibili_integration_settings, parse_bilibili_cookie_header, update_bilibili_integration_settings

router = APIRouter(prefix='/settings', tags=['settings'])


@router.get('/integrations/bilibili')
def bilibili_integration_settings() -> BilibiliIntegrationSettingsEntry:
    return get_bilibili_integration_settings()


@router.put('/integrations/bilibili')
def update_bilibili_settings(payload: BilibiliIntegrationSettingsUpdateRequest) -> BilibiliIntegrationSettingsEntry:
    return update_bilibili_integration_settings(payload)


@router.post('/integrations/bilibili/parse-cookie')
def parse_bilibili_cookie(payload: BilibiliIntegrationSettingsUpdateRequest) -> BilibiliIntegrationCookieParseResponse:
    return parse_bilibili_cookie_header(payload.cookie_header)
