from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError

from app.services import items_service, organization_service


def test_tag_and_collection_routes_fallback_contract(client, monkeypatch) -> None:
    def failing_session_local():
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(items_service, "SessionLocal", failing_session_local)
    monkeypatch.setattr(organization_service, "SessionLocal", failing_session_local)

    import_response = client.post(
        "/api/items/import",
        json={"url": "https://example.com/articles/organization", "source_hint": "article"},
    )
    assert import_response.status_code == 200
    item_id = import_response.json()["item_id"]

    tags_response = client.post(
        f"/api/items/{item_id}/tags",
        json={"tags": ["Research", " video ", "research"]},
    )
    assert tags_response.status_code == 200
    assert tags_response.json()["items"] == [
        {"id": "research", "name": "Research"},
        {"id": "video", "name": "video"},
    ]

    detail_response = client.get(f"/api/items/{item_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["tags"] == [
        {"id": "research", "name": "Research"},
        {"id": "video", "name": "video"},
    ]

    filtered_response = client.get("/api/items?tag=research&page=1&page_size=20")
    assert filtered_response.status_code == 200
    assert filtered_response.json()["items"][0]["id"] == item_id

    collection_response = client.post(
        "/api/collections",
        json={"name": "AI Reading", "description": "Saved materials about AI"},
    )
    assert collection_response.status_code == 200
    collection = collection_response.json()
    assert collection["name"] == "AI Reading"
    assert collection["item_count"] == 0

    add_response = client.post(
        f"/api/collections/{collection['id']}/items",
        json={"item_id": item_id},
    )
    assert add_response.status_code == 200
    assert add_response.json()["item_count"] == 1

    detail_response = client.get(f"/api/items/{item_id}")
    assert detail_response.status_code == 200
    detail_collection = detail_response.json()["collections"][0]
    assert detail_collection["id"] == collection["id"]
    assert detail_collection["name"] == "AI Reading"

    filtered_response = client.get(
        f"/api/items?collection_id={collection['id']}&page=1&page_size=20"
    )
    assert filtered_response.status_code == 200
    assert filtered_response.json()["items"][0]["id"] == item_id

    list_response = client.get("/api/collections")
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["item_count"] == 1

    remove_response = client.delete(f"/api/collections/{collection['id']}/items/{item_id}")
    assert remove_response.status_code == 200
    assert remove_response.json()["item_count"] == 0

    detail_response = client.get(f"/api/items/{item_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["collections"] == []
