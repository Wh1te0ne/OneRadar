from fastapi import APIRouter

from app.schemas.settings import (
    BilibiliIntegrationCookieParseResponse,
    BilibiliIntegrationSettingsEntry,
    BilibiliIntegrationSettingsUpdateRequest,
    BilibiliQrcodeGenerateResponse,
    BilibiliQrcodePollRequest,
    BilibiliQrcodePollResponse,
)
from app.services.bilibili_login_service import generate_bilibili_qrcode, poll_bilibili_qrcode
from app.services.settings_service import (
    get_bilibili_integration_settings,
    parse_bilibili_cookie_header,
    update_bilibili_integration_settings,
)

router = APIRouter(prefix='/settings', tags=['settings'])


@router.get('/integrations/bilibili')
def bilibili_integration_settings() -> BilibiliIntegrationSettingsEntry:
    return get_bilibili_integration_settings()


@router.put('/integrations/bilibili')
def update_bilibili_settings(
    payload: BilibiliIntegrationSettingsUpdateRequest,
) -> BilibiliIntegrationSettingsEntry:
    return update_bilibili_integration_settings(payload)


@router.post('/integrations/bilibili/parse-cookie')
def parse_bilibili_cookie(
    payload: BilibiliIntegrationSettingsUpdateRequest,
) -> BilibiliIntegrationCookieParseResponse:
    return parse_bilibili_cookie_header(payload.cookie_header)


@router.post('/integrations/bilibili/qrcode')
def create_bilibili_qrcode() -> BilibiliQrcodeGenerateResponse:
    return generate_bilibili_qrcode()


@router.post('/integrations/bilibili/qrcode/poll')
def poll_bilibili_qrcode_status(payload: BilibiliQrcodePollRequest) -> BilibiliQrcodePollResponse:
    return poll_bilibili_qrcode(payload)
