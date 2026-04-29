from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.store import STORE


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_store() -> None:
    STORE.users.clear()
    STORE.items.clear()
    STORE.tasks.clear()
    STORE.providers.clear()
    STORE.folders.clear()
    STORE.integrations.clear()
    STORE.podcast_subscriptions.clear()
    STORE.collections.clear()
    yield
    STORE.users.clear()
    STORE.items.clear()
    STORE.tasks.clear()
    STORE.providers.clear()
    STORE.folders.clear()
    STORE.integrations.clear()
    STORE.podcast_subscriptions.clear()
    STORE.collections.clear()
