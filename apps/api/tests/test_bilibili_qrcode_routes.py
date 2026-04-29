from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError

from app.services import bilibili_login_service, settings_service


def test_generate_bilibili_qrcode_route_returns_login_payload(client, monkeypatch) -> None:
    def fake_generate():
        return {
            "url": "https://passport.bilibili.com/h5-app/passport/login/scan?qrcode_key=test-key",
            "qrcode_key": "test-key",
        }

    monkeypatch.setattr(bilibili_login_service, "_request_qrcode_generate", fake_generate)

    response = client.post("/api/settings/integrations/bilibili/qrcode")

    assert response.status_code == 200
    body = response.json()
    assert body["url"].startswith("https://passport.bilibili.com/")
    assert body["qrcode_key"] == "test-key"
    assert body["expires_in_seconds"] == 180


def test_poll_bilibili_qrcode_success_saves_cookies_without_echoing_secrets(
    client,
    monkeypatch,
) -> None:
    def failing_session_local():
        raise SQLAlchemyError("database unavailable")

    def fake_poll(qrcode_key: str):
        assert qrcode_key == "test-key"
        return (
            {"code": 0, "message": "扫码登录成功", "refresh_token": "refresh-secret"},
            [
                "SESSDATA=sess-secret; Domain=.bilibili.com; Path=/; HttpOnly",
                "bili_jct=jct-secret; Domain=.bilibili.com; Path=/",
                "buvid3=buvid-secret; Domain=.bilibili.com; Path=/",
            ],
        )

    monkeypatch.setattr(settings_service, "SessionLocal", failing_session_local)
    monkeypatch.setattr(
        bilibili_login_service.settings_service,
        "SessionLocal",
        failing_session_local,
    )
    monkeypatch.setattr(bilibili_login_service, "_request_qrcode_poll", fake_poll)

    response = client.post(
        "/api/settings/integrations/bilibili/qrcode/poll",
        json={"qrcode_key": "test-key"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "confirmed"
    assert body["code"] == 0
    assert body["message"] == "扫码登录成功"
    assert body["saved_cookie"] is not None
    assert body["saved_cookie"]["ready_for_authenticated_fetch"] is True
    assert "sess-secret" not in response.text
    assert "jct-secret" not in response.text
    assert "buvid-secret" not in response.text


def test_update_bilibili_settings_saves_visual_enhancement_flag(client, monkeypatch) -> None:
    def failing_session_local():
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(settings_service, "SessionLocal", failing_session_local)

    response = client.put(
        "/api/settings/integrations/bilibili",
        json={"is_enabled": False, "visual_enhancement_enabled": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["is_enabled"] is False
    assert body["visual_enhancement_enabled"] is True

    followup = client.get("/api/settings/integrations/bilibili")
    assert followup.status_code == 200
    assert followup.json()["visual_enhancement_enabled"] is True
