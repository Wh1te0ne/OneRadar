from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class Settings:
    app_name: str = "one-radar-worker"
    environment: str = "development"
    log_level: str = "INFO"
    queue_backend: str = "redis"
    redis_url: str = "redis://localhost:6379/0"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/oneradar"
    storage_root: Path = Path("./data")
    enable_dry_run: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        storage_root = Path(os.getenv("ONERADAR_STORAGE_ROOT", "./data"))
        return cls(
            app_name=os.getenv("ONERADAR_APP_NAME", "one-radar-worker"),
            environment=os.getenv("ONERADAR_ENV", "development"),
            log_level=os.getenv("ONERADAR_LOG_LEVEL", "INFO"),
            queue_backend=os.getenv("ONERADAR_QUEUE_BACKEND", "redis"),
            redis_url=os.getenv("ONERADAR_REDIS_URL", "redis://localhost:6379/0"),
            database_url=os.getenv(
                "ONERADAR_DATABASE_URL",
                "postgresql+psycopg://postgres:postgres@localhost:5432/oneradar",
            ),
            storage_root=storage_root,
            enable_dry_run=_as_bool(os.getenv("ONERADAR_ENABLE_DRY_RUN"), True),
        )
