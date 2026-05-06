from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError

from app.services import items_service, providers_service


class _FakeImageHeaders:
    def get_content_type(self) -> str:
        return "image/jpeg"


class _FakeImageResponse:
    headers = _FakeImageHeaders()

    def __enter__(self) -> "_FakeImageResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def read(self) -> bytes:
        return b"fake-jpeg"


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


def test_bilibili_preview_returns_metadata_without_importing(client, monkeypatch) -> None:
    def fake_fetch(video_id: str, id_type: str) -> dict[str, object]:
        assert video_id == "BV1xx411c7mD"
        assert id_type == "bvid"
        return {
            "code": 0,
            "data": {
                "bvid": "BV1xx411c7mD",
                "aid": 170001,
                "cid": 280001,
                "title": "测试视频标题",
                "pic": "http://i0.hdslb.com/bfs/archive/test.jpg",
                "desc": "这是一段简介",
                "duration": 3661,
                "pubdate": 1710000000,
                "owner": {"name": "测试 UP", "mid": 42},
                "pages": [
                    {"page": 1, "part": "第一部分", "cid": 280001},
                    {"page": 2, "part": "第二部分", "cid": 280002},
                ],
            },
        }

    monkeypatch.setattr(items_service, "_fetch_bilibili_view_payload", fake_fetch, raising=False)

    response = client.post(
        "/api/items/bilibili/preview",
        json={"url": "https://www.bilibili.com/video/BV1xx411c7mD/?spm_id_from=333.1007"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["content_type"] == "bilibili_video"
    assert body["normalized_url"] == "https://www.bilibili.com/video/BV1xx411c7mD/"
    assert body["title"] == "测试视频标题"
    assert body["owner_name"] == "测试 UP"
    assert body["cover_url"] == "https://i0.hdslb.com/bfs/archive/test.jpg"
    assert body["duration_seconds"] == 3661
    assert body["duration_text"] == "1:01:01"
    assert body["bvid"] == "BV1xx411c7mD"
    assert body["cid"] == 280001
    assert body["page_count"] == 2
    assert items_service.STORE.items == {}


def test_bilibili_cover_route_proxies_hdslb_image(client, monkeypatch) -> None:
    seen_headers = {}

    def fake_urlopen(request, timeout: int = 10) -> _FakeImageResponse:
        assert timeout == 10
        assert request.full_url == "https://i0.hdslb.com/bfs/archive/test.jpg"
        seen_headers.update(request.headers)
        return _FakeImageResponse()

    monkeypatch.setattr(items_service, "urlopen", fake_urlopen)

    response = client.get(
        "/api/items/bilibili/cover",
        params={"url": "http://i0.hdslb.com/bfs/archive/test.jpg"},
    )

    assert response.status_code == 200
    assert response.content == b"fake-jpeg"
    assert response.headers["content-type"] == "image/jpeg"
    assert seen_headers["Referer"] == "https://www.bilibili.com/"


def test_bilibili_cover_route_rejects_non_hdslb_hosts(client) -> None:
    response = client.get(
        "/api/items/bilibili/cover",
        params={"url": "https://example.com/cover.jpg"},
    )

    assert response.status_code == 400


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


def test_delete_moves_item_to_recently_deleted_and_restore_purge(client, monkeypatch) -> None:
    def failing_session_local():
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(items_service, "SessionLocal", failing_session_local)

    import_response = client.post(
        "/api/items/import",
        json={"url": "https://example.com/articles/delete-me", "source_hint": "article"},
    )
    assert import_response.status_code == 200
    item_id = import_response.json()["item_id"]

    task_response = client.post(f"/api/items/{item_id}/summaries/generate")
    assert task_response.status_code == 200
    task_id = task_response.json()["task_id"]

    delete_response = client.delete(f"/api/items/{item_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True

    canceled_task_response = client.get(f"/api/tasks/{task_id}")
    assert canceled_task_response.status_code == 200
    canceled_task = canceled_task_response.json()
    assert canceled_task["status"] == "canceled"
    assert canceled_task["error_message"] == "content item was deleted"

    list_response = client.get("/api/items?page=1&page_size=20")
    assert list_response.status_code == 200
    assert all(item["id"] != item_id for item in list_response.json()["items"])

    detail_response = client.get(f"/api/items/{item_id}")
    assert detail_response.status_code == 404

    trash_response = client.get("/api/items/trash?page_size=20")
    assert trash_response.status_code == 200
    trash_items = trash_response.json()["items"]
    assert any(item["id"] == item_id and item["deleted_at"] and item["delete_expires_at"] for item in trash_items)

    restore_response = client.post(f"/api/items/trash/{item_id}/restore")
    assert restore_response.status_code == 200
    assert restore_response.json()["deleted"] is False

    list_response = client.get("/api/items?page=1&page_size=20")
    assert any(item["id"] == item_id for item in list_response.json()["items"])

    delete_response = client.delete(f"/api/items/{item_id}")
    assert delete_response.status_code == 200
    purge_response = client.delete(f"/api/items/trash/{item_id}/purge")
    assert purge_response.status_code == 200
    assert purge_response.json()["deleted"] is True
    assert client.get(f"/api/items/{item_id}").status_code == 404


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


def test_import_item_can_persist_rss_preview_and_queue_summary(client, monkeypatch) -> None:
    def failing_session_local():
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(items_service, "SessionLocal", failing_session_local)

    response = client.post(
        "/api/items/import",
        json={
            "url": "https://example.com/articles/rss-preview",
            "source_hint": "article",
            "title": "RSS Preview Title",
            "site_title": "Example Feed",
            "author": "Feed Author",
            "summary": "Feed-provided summary",
            "parsed_text": "First paragraph.\n\nSecond paragraph.",
            "parser_name": "feed-preview",
            "parser_version": "v1",
            "generate_summary": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert body["task_id"]

    item_id = body["item_id"]
    detail_response = client.get(f"/api/items/{item_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["title"] == "RSS Preview Title"
    assert detail["metadata"]["author_name"] == "Feed Author"
    assert detail["metadata"]["site_name"] == "Example Feed"
    assert detail["parsed_document"]["plain_text"] == "First paragraph.\n\nSecond paragraph."

    task_response = client.get(f"/api/tasks/{body['task_id']}")
    assert task_response.status_code == 200
    assert task_response.json()["task_type"] == "generate_summary"


def test_import_item_updates_existing_rss_preview_metadata(client, monkeypatch) -> None:
    def failing_session_local():
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(items_service, "SessionLocal", failing_session_local)

    first_response = client.post(
        "/api/items/import",
        json={"url": "https://example.com/articles/duplicate-preview", "source_hint": "article"},
    )
    assert first_response.status_code == 200
    item_id = first_response.json()["item_id"]

    second_response = client.post(
        "/api/items/import",
        json={
            "url": "https://example.com/articles/duplicate-preview",
            "source_hint": "article",
            "title": "Updated RSS Title",
            "site_title": "Updated Feed",
            "parsed_text": "Updated persisted text.",
            "generate_summary": True,
        },
    )
    assert second_response.status_code == 200
    second_body = second_response.json()
    assert second_body["is_duplicate"] is True
    assert second_body["item_id"] == item_id
    assert second_body["task_id"]

    detail_response = client.get(f"/api/items/{item_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["title"] == "Updated RSS Title"
    assert detail["metadata"]["site_name"] == "Updated Feed"
    assert detail["parsed_document"]["plain_text"] == "Updated persisted text."


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
