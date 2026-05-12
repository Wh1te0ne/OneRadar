from __future__ import annotations


def test_workspace_bootstrap_requires_login_for_private_accounts(client) -> None:
    response = client.get("/api/auth/bootstrap")

    assert response.status_code == 200
    body = response.json()
    assert body["single_user_mode"] is False
    assert body["requires_login"] is True
    assert body["primary_user"]["username"] == "whiteone"
    assert body["default_inbox_folder"]["name"] == "稍后阅读"


def test_login_accepts_username_and_returns_session(client) -> None:
    login_response = client.post(
        "/api/auth/login",
        json={"identifier": "whiteone", "password": "test-password-only"},
    )
    logout_response = client.post("/api/auth/logout")

    assert login_response.status_code == 200
    assert login_response.json()["user"]["username"] == "whiteone"
    assert login_response.json()["token"]
    assert logout_response.status_code == 404
