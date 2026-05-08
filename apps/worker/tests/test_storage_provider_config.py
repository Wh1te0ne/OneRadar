from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import create_engine

from one_radar_worker.storage import (
    load_summary_provider_config,
    metadata,
    model_providers,
)


def test_summary_provider_config_includes_runtime_provider_config() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata.create_all(engine)
    user_id = uuid4()
    provider_id = uuid4()
    now = datetime.now(UTC)

    with engine.begin() as conn:
        conn.execute(
            model_providers.insert().values(
                id=provider_id,
                user_id=user_id,
                provider_name="DeepSeek",
                provider_type="deepseek",
                display_name="DeepSeek",
                base_url="https://api.deepseek.com/v1",
                api_key_encrypted="plain-key",
                chat_model="deepseek-chat",
                embedding_model=None,
                transcription_model=None,
                is_enabled=True,
                is_builtin=False,
                config={"capability": "llm", "llm": {"thinking_mode": "enabled"}},
                last_test_status=None,
                last_tested_at=None,
                created_at=now,
                updated_at=now,
            )
        )

    config = load_summary_provider_config(engine, str(user_id))

    assert config["provider_id"] == str(provider_id)
    assert config["provider_config"] == {
        "capability": "llm",
        "llm": {"thinking_mode": "enabled"},
    }
