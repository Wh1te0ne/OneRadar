from __future__ import annotations

import json
from http.cookies import SimpleCookie
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from fastapi import HTTPException

from app.schemas.settings import (
    BilibiliIntegrationSettingsUpdateRequest,
    BilibiliQrcodeGenerateResponse,
    BilibiliQrcodePollRequest,
    BilibiliQrcodePollResponse,
)
from app.services import settings_service

QRCODE_GENERATE_URL = 'https://passport.bilibili.com/x/passport-login/web/qrcode/generate'
QRCODE_POLL_URL = 'https://passport.bilibili.com/x/passport-login/web/qrcode/poll'
QRCODE_EXPIRES_IN_SECONDS = 180

POLL_STATE_BY_CODE = {
    0: 'confirmed',
    86038: 'expired',
    86090: 'scanned',
    86101: 'waiting',
}


def _request_json(url: str) -> tuple[dict[str, object], list[str]]:
    request = Request(
        url,
        headers={
            'User-Agent': 'OneRadar/0.1 Bilibili QR Login',
            'Accept': 'application/json, text/plain, */*',
            'Referer': 'https://www.bilibili.com/',
        },
    )
    try:
        with build_opener().open(request, timeout=15) as response:
            raw_body = response.read().decode('utf-8')
            payload = json.loads(raw_body)
            set_cookie_headers = response.headers.get_all('Set-Cookie') or []
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail='Bilibili 登录接口暂时不可用') from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail='Bilibili 登录接口返回了无效数据')
    return payload, list(set_cookie_headers)


def _request_qrcode_generate() -> dict[str, str]:
    payload, _ = _request_json(QRCODE_GENERATE_URL)
    if payload.get('code') != 0:
        raise HTTPException(status_code=502, detail='Bilibili 二维码生成失败')
    data = payload.get('data')
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail='Bilibili 二维码响应缺少 data')

    qrcode_url = data.get('url')
    qrcode_key = data.get('qrcode_key')
    if not isinstance(qrcode_url, str) or not isinstance(qrcode_key, str):
        raise HTTPException(status_code=502, detail='Bilibili 二维码响应缺少关键字段')
    return {'url': qrcode_url, 'qrcode_key': qrcode_key}


def _request_qrcode_poll(qrcode_key: str) -> tuple[dict[str, object], list[str]]:
    url = QRCODE_POLL_URL + '?' + urlencode({'qrcode_key': qrcode_key})
    payload, set_cookie_headers = _request_json(url)
    if payload.get('code') != 0:
        raise HTTPException(status_code=502, detail='Bilibili 二维码轮询失败')
    data = payload.get('data')
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail='Bilibili 二维码轮询响应缺少 data')
    return data, set_cookie_headers


def _cookie_header_from_set_cookie(headers: list[str]) -> str:
    values: dict[str, str] = {}
    for header in headers:
        cookie = SimpleCookie()
        try:
            cookie.load(header)
        except Exception:
            continue
        for key in settings_service.COOKIE_KEYS:
            morsel = cookie.get(key)
            if morsel is not None and morsel.value:
                values[key] = morsel.value
    return '; '.join(f'{key}={value}' for key, value in values.items())


def generate_bilibili_qrcode() -> BilibiliQrcodeGenerateResponse:
    payload = _request_qrcode_generate()
    return BilibiliQrcodeGenerateResponse(
        url=payload['url'],
        qrcode_key=payload['qrcode_key'],
        expires_in_seconds=QRCODE_EXPIRES_IN_SECONDS,
    )


def poll_bilibili_qrcode(payload: BilibiliQrcodePollRequest) -> BilibiliQrcodePollResponse:
    data, set_cookie_headers = _request_qrcode_poll(payload.qrcode_key)
    raw_code = data.get('code')
    code = raw_code if isinstance(raw_code, int) else -1
    state = POLL_STATE_BY_CODE.get(code, 'failed')
    message = data.get('message') if isinstance(data.get('message'), str) else '未知状态'
    saved_cookie = None

    if code == 0:
        cookie_header = _cookie_header_from_set_cookie(set_cookie_headers)
        if not cookie_header:
            raise HTTPException(status_code=502, detail='Bilibili 登录成功但未返回可保存的 Cookie')
        saved_cookie = settings_service.update_bilibili_integration_settings(
            BilibiliIntegrationSettingsUpdateRequest(is_enabled=True, cookie_header=cookie_header)
        )

    return BilibiliQrcodePollResponse(
        code=code,
        state=state,
        message=message,
        saved_cookie=saved_cookie,
    )
