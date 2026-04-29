from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError

from app.services import items_service, providers_service


def test_import_item_route_fallback_contract_and_deduplication(client, monkeypatch) -> None:
    def failing_session_local():
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(items_service, "SessionLocal", failing_session_local)

    source_url = "https://example.com/articles/test?utm_source=newsletter&utm_medium=email"
    first_response = client.post(
        "/api/items/import",
        json={"url": source_url, "source_hint": "article"},
    )

    assert first_response.status_code == 200
    first_body = first_response.json()
    assert first_body["status"] == "pending"
    assert first_body["content_type"] == "article"
    assert first_body["folder_id"] == "inbox"
    assert first_body["folder_name"] == "稍后阅读"
    assert first_body["is_duplicate"] is False
    assert first_body["uid"] == first_body["item_id"]
    assert first_body["task_id"]

    duplicate_response = client.post(
        "/api/items/import",
        json={"url": "https://example.com/articles/test", "source_hint": "article"},
    )

    assert duplicate_response.status_code == 200
    duplicate_body = duplicate_response.json()
    assert duplicate_body["status"] == "already_exists"
    assert duplicate_body["is_duplicate"] is True
    assert duplicate_body["existing_uid"] == first_body["uid"]
    assert duplicate_body["task_id"] is None
    assert duplicate_body["uid"] == first_body["uid"]


def test_update_reading_state_route_fallback_contract(client, monkeypatch) -> None:
    def failing_session_local():
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(items_service, "SessionLocal", failing_session_local)

    import_response = client.post(
        "/api/items/import",
        json={"url": "https://example.com/articles/progress", "source_hint": "article"},
    )
    assert import_response.status_code == 200
    item_id = import_response.json()["item_id"]

    update_response = client.put(
        f"/api/items/{item_id}/reading-state",
        json={"progress_percent": 42, "is_favorited": True},
    )
    assert update_response.status_code == 200
    update_body = update_response.json()
    assert update_body["progress_percent"] == 42
    assert update_body["is_favorited"] is True
    assert update_body["is_archived"] is False
    assert update_body["last_read_at"]

    detail_response = client.get(f"/api/items/{item_id}")
    assert detail_response.status_code == 200
    detail_body = detail_response.json()
    assert detail_body["reading_state"]["progress_percent"] == 42
    assert detail_body["reading_state"]["is_favorited"] is True

    list_response = client.get("/api/items?page=1&page_size=20")
    assert list_response.status_code == 200
    list_body = list_response.json()
    assert list_body["items"][0]["progress_percent"] == 42
    assert list_body["items"][0]["is_read"] is False

    complete_response = client.put(
        f"/api/items/{item_id}/reading-state",
        json={"progress_percent": 100},
    )
    assert complete_response.status_code == 200
    assert complete_response.json()["progress_percent"] == 100

    list_response = client.get("/api/items?page=1&page_size=20")
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["is_read"] is True


def test_generate_summary_route_creates_task(client, monkeypatch) -> None:
    def failing_session_local():
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(items_service, "SessionLocal", failing_session_local)

    import_response = client.post(
        "/api/items/import",
        json={"url": "https://example.com/articles/summary", "source_hint": "article"},
    )
    assert import_response.status_code == 200
    item_id = import_response.json()["item_id"]

    response = client.post(f"/api/items/{item_id}/summaries/generate")

    assert response.status_code == 200
    body = response.json()
    assert body["item_id"] == item_id
    assert body["task_id"]
    assert body["status"] == "pending"

    task_response = client.get(f"/api/tasks/{body['task_id']}")
    assert task_response.status_code == 200
    assert task_response.json()["task_type"] == "generate_summary"


def test_provider_route_preserves_editable_doubao_transcription_credentials(
    client,
    monkeypatch,
) -> None:
    def failing_session_local():
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(providers_service, "SessionLocal", failing_session_local)

    create_response = client.post(
        "/api/providers",
        json={
            "provider_name": "Doubao",
            "provider_type": "doubao",
            "base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "api_key": "chat-secret",
            "chat_model": "ep-chat",
            "transcription_app_id": "9058439082",
            "transcription_access_token": "access-token",
            "transcription_secret_key": "secret-key",
            "is_enabled": True,
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()
    assert created["transcription_app_id"] == "9058439082"
    assert created["transcription_access_token_configured"] is True
    assert created["transcription_secret_key_configured"] is True

    update_response = client.put(
        f"/api/providers/{created['id']}",
        json={
            "provider_name": "Doubao",
            "provider_type": "doubao",
            "base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "chat_model": "ep-chat-2",
            "transcription_app_id": "9058439082",
            "is_enabled": True,
        },
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["chat_model"] == "ep-chat-2"
    assert updated["transcription_app_id"] == "9058439082"
    assert updated["transcription_access_token_configured"] is True
    assert updated["transcription_secret_key_configured"] is True
