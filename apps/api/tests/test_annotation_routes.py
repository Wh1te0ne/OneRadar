from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError

from app.services import annotations_service, items_service


def test_highlight_and_note_routes_fallback_contract(client, monkeypatch) -> None:
    def failing_session_local():
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(items_service, "SessionLocal", failing_session_local)
    monkeypatch.setattr(annotations_service, "SessionLocal", failing_session_local)

    import_response = client.post(
        "/api/items/import",
        json={"url": "https://example.com/articles/annotations", "source_hint": "article"},
    )
    assert import_response.status_code == 200
    item_id = import_response.json()["item_id"]

    highlight_response = client.post(
        f"/api/items/{item_id}/highlights",
        json={
            "quote_text": "important sentence",
            "anchor_type": "article_text",
            "start_anchor": "p3",
            "end_anchor": "p3",
            "start_offset": 10,
            "end_offset": 28,
            "color": "yellow",
        },
    )
    assert highlight_response.status_code == 200
    highlight = highlight_response.json()
    assert highlight["item_id"] == item_id
    assert highlight["quote_text"] == "important sentence"
    assert highlight["anchor_type"] == "article_text"
    assert highlight["start_anchor"] == "p3"
    assert highlight["color"] == "yellow"

    highlights_response = client.get(f"/api/items/{item_id}/highlights")
    assert highlights_response.status_code == 200
    assert highlights_response.json()["items"][0]["id"] == highlight["id"]

    note_response = client.post(
        f"/api/items/{item_id}/notes",
        json={"highlight_id": highlight["id"], "content": "My note"},
    )
    assert note_response.status_code == 200
    note = note_response.json()
    assert note["item_id"] == item_id
    assert note["highlight_id"] == highlight["id"]
    assert note["content"] == "My note"

    detail_response = client.get(f"/api/items/{item_id}")
    assert detail_response.status_code == 200
    detail_body = detail_response.json()
    assert detail_body["highlights"][0]["note_id"] == note["id"]
    assert detail_body["notes"][0]["content"] == "My note"

    update_response = client.put(f"/api/notes/{note['id']}", json={"content": "Updated note"})
    assert update_response.status_code == 200
    assert update_response.json()["content"] == "Updated note"

    delete_response = client.delete(f"/api/notes/{note['id']}")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True

    detail_response = client.get(f"/api/items/{item_id}")
    assert detail_response.status_code == 200
    detail_body = detail_response.json()
    assert detail_body["highlights"][0]["note_id"] is None
    assert detail_body["notes"] == []

    delete_highlight_response = client.delete(f"/api/highlights/{highlight['id']}")
    assert delete_highlight_response.status_code == 200
    assert delete_highlight_response.json()["deleted"] is True

    detail_response = client.get(f"/api/items/{item_id}")
    assert detail_response.status_code == 200
    detail_body = detail_response.json()
    assert detail_body["highlights"] == []
