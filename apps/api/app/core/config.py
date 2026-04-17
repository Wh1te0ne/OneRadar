from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "OneRadar API"
    api_prefix: str = "/api"
    environment: str = "development"
    version: str = "v1"
    cors_origins: list[str] = ["*"]
    database_url: str = "sqlite+pysqlite:///./oneradar.db"
    redis_url: str = "redis://localhost:6379/0"
    api_secret_key: str = "change-me"

    model_config = SettingsConfigDict(
        env_prefix="ONERADAR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
