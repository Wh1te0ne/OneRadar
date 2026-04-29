from __future__ import annotations


def test_workspace_bootstrap_is_single_user_without_login(client) -> None:
    response = client.get("/api/auth/bootstrap")

    assert response.status_code == 200
    body = response.json()
    assert body["single_user_mode"] is True
    assert body["requires_login"] is False
    assert body["primary_user"]["username"] == "local"
    assert body["default_inbox_folder"]["name"] == "稍后阅读"


def test_login_and_logout_are_not_public_v1_routes(client) -> None:
    login_response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "secret"},
    )
    logout_response = client.post("/api/auth/logout")

    assert login_response.status_code == 404
    assert logout_response.status_code == 404
