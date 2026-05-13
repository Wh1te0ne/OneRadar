from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_integration_token_can_call_mcp_without_browser_session(client) -> None:
    created = client.post(
        "/api/integration-tokens",
        json={"name": "Hermes MCP", "scopes": ["mcp:read"]},
    )

    assert created.status_code == 200, created.json()
    body = created.json()
    assert body["token"].startswith("ort_")
    assert body["item"]["name"] == "Hermes MCP"
    assert body["item"]["scopes"] == ["mcp:read"]
    assert body["item"]["token_prefix"] == body["token"][:12]

    token_client = TestClient(app)
    token_client.headers.update({"Authorization": f"Bearer {body['token']}"})
    response = token_client.post(
        "/api/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )

    assert response.status_code == 200, response.json()
    tool_names = {tool["name"] for tool in response.json()["result"]["tools"]}
    assert {"get_news_window", "get_news_window_status", "get_news_sources"} <= tool_names


def test_integration_token_is_only_shown_once(client) -> None:
    created = client.post(
        "/api/integration-tokens",
        json={"name": "Hermes MCP", "scopes": ["mcp:read"]},
    )

    assert created.status_code == 200, created.json()
    listed = client.get("/api/integration-tokens")

    assert listed.status_code == 200, listed.json()
    assert listed.json()["items"][0]["name"] == "Hermes MCP"
    assert "token" not in listed.json()["items"][0]


def test_revoked_integration_token_cannot_call_mcp(client) -> None:
    created = client.post(
        "/api/integration-tokens",
        json={"name": "Hermes MCP", "scopes": ["mcp:read"]},
    )
    assert created.status_code == 200, created.json()
    token = created.json()["token"]
    token_id = created.json()["item"]["id"]

    revoked = client.delete(f"/api/integration-tokens/{token_id}")
    assert revoked.status_code == 200, revoked.json()
    assert revoked.json()["revoked"] is True
    listed = client.get("/api/integration-tokens")
    assert listed.status_code == 200, listed.json()
    assert all(item["id"] != token_id for item in listed.json()["items"])

    token_client = TestClient(app)
    token_client.headers.update({"Authorization": f"Bearer {token}"})
    response = token_client.post(
        "/api/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )

    assert response.status_code == 401


def test_mcp_rejects_missing_credentials() -> None:
    anonymous_client = TestClient(app)
    response = anonymous_client.post(
        "/api/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )

    assert response.status_code == 401
