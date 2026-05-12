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
    bootstrap_username: str = "whiteone"
    bootstrap_email: str | None = None
    bootstrap_password: str | None = None
    auth_token_ttl_seconds: int = 60 * 60 * 24 * 30
    feed_refresh_enabled: bool = True
    feed_refresh_interval_seconds: int = 1800
    feed_refresh_startup_delay_seconds: int = 20
    daily_news_generation_enabled: bool = True
    daily_news_generation_hour: int = 10
    daily_news_generation_timezone: str = "Asia/Shanghai"

    model_config = SettingsConfigDict(
        env_prefix="ONERADAR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
