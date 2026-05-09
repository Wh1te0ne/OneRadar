from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock

from app.schemas.common import ContentType, ItemStatus, ProviderType, TaskStatus


def now_utc() -> datetime:
    return datetime.now(UTC)


def to_iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


@dataclass
class InMemoryStore:
    users: dict[str, dict[str, object]] = field(default_factory=dict)
    items: dict[str, dict[str, object]] = field(default_factory=dict)
    tasks: dict[str, dict[str, object]] = field(default_factory=dict)
    providers: dict[str, dict[str, object]] = field(default_factory=dict)
    folders: dict[str, dict[str, object]] = field(default_factory=dict)
    integrations: dict[str, dict[str, object]] = field(default_factory=dict)
    podcast_subscriptions: dict[str, dict[str, object]] = field(default_factory=dict)
    collections: dict[str, dict[str, object]] = field(default_factory=dict)
    daily_reports: dict[str, dict[str, object]] = field(default_factory=dict)
    lock: Lock = field(default_factory=Lock)


STORE = InMemoryStore()


def seed_store() -> None:
    with STORE.lock:
        if STORE.users:
            return
        STORE.users["user-1"] = {
            "id": "user-1",
            "username": "local",
            "created_at": now_utc(),
        }
        STORE.providers["provider-1"] = {
            "id": "provider-1",
            "provider_name": "Doubao",
            "provider_type": ProviderType.doubao,
            "base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "chat_model": "ep-20260304161530-6ffr5",
            "embedding_model": "doubao-embed",
            "transcription_model": None,
            "is_enabled": False,
            "config": {"capability": "llm"},
            "last_test_status": None,
            "last_tested_at": None,
        }
        STORE.folders["inbox"] = {
            "id": "inbox",
            "name": "稍后阅读",
            "is_builtin": True,
            "created_at": now_utc(),
            "updated_at": now_utc(),
        }
        STORE.items["item-1"] = {
            "id": "item-1",
            "uid": "item-1",
            "title": "Example Article",
            "content_type": ContentType.article,
            "source_url": "https://example.com/article",
            "folder_id": "inbox",
            "folder_name": "稍后阅读",
            "is_inbox": True,
            "status": ItemStatus.completed,
            "metadata": {
                "author_name": "Author",
                "published_at": "2026-04-12T10:00:00Z",
                "site_name": "Example",
            },
            "parsed_document": {
                "plain_text": "Readable article text...",
                "structured_blocks": [],
                "parser_name": "readability",
                "parser_version": "v1",
            },
            "transcript": None,
            "summaries": [
                {
                    "summary_type": "one_line",
                    "content": "Short conclusion.",
                    "model_name": "doubao-chat",
                    "version": 1,
                }
            ],
            "highlights": [],
            "notes": [],
            "tags": [],
            "collections": [],
            "reading_state": {
                "progress_percent": 0,
                "is_read": False,
                "last_read_at": None,
                "is_archived": False,
                "is_favorited": False,
            },
            "created_at": now_utc(),
            "updated_at": now_utc(),
        }
        STORE.tasks["task-1"] = {
            "id": "task-1",
            "item_id": "item-1",
            "task_type": "extract_article",
            "status": TaskStatus.pending,
            "attempt_count": 0,
            "error_message": None,
            "created_at": now_utc(),
        }

