from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError

from app.services import items_service


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
