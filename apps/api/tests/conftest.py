from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("ONERADAR_BOOTSTRAP_PASSWORD", "test-password-only")

from app.db.base import Base
from app.db.session import engine
from app.main import app
from app.schemas.common import ProviderType
from app.services.store import STORE

Base.metadata.create_all(engine)


@pytest.fixture
def client() -> TestClient:
    test_client = TestClient(app)
    response = test_client.post(
        "/api/auth/login",
        json={"identifier": "whiteone", "password": "test-password-only"},
    )
    if response.status_code == 200:
        test_client.headers.update({"Authorization": f"Bearer {response.json()['token']}"})
        test_client.post(
            "/api/providers",
            json={
                "provider_name": f"Test LLM {uuid4()}",
                "provider_type": "custom",
                "base_url": "https://example.com/v1",
                "api_key": "test-api-key",
                "chat_model": "test-chat",
                "is_enabled": True,
            },
        )
    STORE.providers["provider-test"] = {
        "id": "provider-test",
        "provider_name": "Test LLM",
        "provider_type": ProviderType.custom,
        "base_url": "https://example.com/v1",
        "chat_model": "test-chat",
        "embedding_model": None,
        "transcription_model": None,
        "is_enabled": True,
        "config": {"capability": "llm"},
        "last_test_status": None,
        "last_tested_at": None,
    }
    return test_client


@pytest.fixture(autouse=True)
def reset_store() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    STORE.users.clear()
    STORE.items.clear()
    STORE.tasks.clear()
    STORE.providers.clear()
    STORE.folders.clear()
    STORE.integrations.clear()
    STORE.podcast_subscriptions.clear()
    STORE.collections.clear()
    STORE.daily_reports.clear()
    yield
    STORE.users.clear()
    STORE.items.clear()
    STORE.tasks.clear()
    STORE.providers.clear()
    STORE.folders.clear()
    STORE.integrations.clear()
    STORE.podcast_subscriptions.clear()
    STORE.collections.clear()
    STORE.daily_reports.clear()
