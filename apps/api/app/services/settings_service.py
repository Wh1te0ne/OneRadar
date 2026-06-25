from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from http.cookies import SimpleCookie
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db.models import IntegrationSetting
from app.db.session import SessionLocal
from app.schemas.settings import (
    BilibiliIntegrationCookieParseResponse,
    BilibiliIntegrationSettingsEntry,
    BilibiliIntegrationSettingsUpdateRequest,
    FeedRefreshSettingsEntry,
    FeedRefreshSettingsUpdateRequest,
    IntegrationSecretStatus,
)
from app.services.db_access import get_bilibili_integration_setting, get_primary_user
from app.services.store import STORE, seed_store

BILIBILI_INTEGRATION_KEY = 'bilibili'
BILIBILI_DISPLAY_NAME = 'Bilibili'
FEED_REFRESH_SETTINGS_KEY = 'feed_refresh'
FEED_REFRESH_DISPLAY_NAME = 'RSS 自动刷新'
COOKIE_KEYS = {
    'SESSDATA': 'sessdata',
    'bili_jct': 'bili_jct',
    'buvid3': 'buvid3',
}


@dataclass(frozen=True, slots=True)
class FeedRefreshRuntimeSettings:
    enabled: bool
    interval_value: int
    interval_unit: str

    @property
    def interval_seconds(self) -> int:
        multiplier = 3600 if self.interval_unit == "hours" else 60
        return self.interval_value * multiplier


def _normalize_secret(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return '*' * len(value)
    return f'{value[:4]}...{value[-4:]}'


def _default_feed_refresh_runtime_settings() -> FeedRefreshRuntimeSettings:
    settings = get_settings()
    seconds = max(60, int(settings.feed_refresh_interval_seconds))
    if seconds % 3600 == 0:
        hours = max(1, min(24, seconds // 3600))
        return FeedRefreshRuntimeSettings(
            enabled=bool(settings.feed_refresh_enabled),
            interval_value=hours,
            interval_unit="hours",
        )
    minutes = max(1, min(60, round(seconds / 60)))
    return FeedRefreshRuntimeSettings(
        enabled=bool(settings.feed_refresh_enabled),
        interval_value=minutes,
        interval_unit="minutes",
    )


def _validate_feed_refresh_settings(
    enabled: bool,
    interval_value: int,
    interval_unit: str,
) -> FeedRefreshRuntimeSettings:
    if interval_unit not in {"minutes", "hours"}:
        raise ValueError("刷新单位只支持分钟或小时。")
    if interval_unit == "minutes" and not 1 <= interval_value <= 60:
        raise ValueError("分钟间隔必须在 1 到 60 之间。")
    if interval_unit == "hours" and not 1 <= interval_value <= 24:
        raise ValueError("小时间隔必须在 1 到 24 之间。")
    return FeedRefreshRuntimeSettings(
        enabled=enabled,
        interval_value=interval_value,
        interval_unit=interval_unit,
    )


def _feed_refresh_entry_from_runtime(
    settings: FeedRefreshRuntimeSettings,
    updated_at: datetime | None = None,
) -> FeedRefreshSettingsEntry:
    return FeedRefreshSettingsEntry(
        enabled=settings.enabled,
        interval_value=settings.interval_value,
        interval_unit=settings.interval_unit,  # type: ignore[arg-type]
        interval_seconds=settings.interval_seconds,
        updated_at=updated_at,
    )


def _runtime_from_feed_refresh_config(
    config: dict[str, Any],
    enabled: bool,
) -> FeedRefreshRuntimeSettings:
    default = _default_feed_refresh_runtime_settings()
    interval_unit = str(config.get("interval_unit") or default.interval_unit)
    try:
        interval_value = int(config.get("interval_value") or default.interval_value)
    except (TypeError, ValueError):
        interval_value = default.interval_value
    return _validate_feed_refresh_settings(enabled, interval_value, interval_unit)


def get_feed_refresh_runtime_settings() -> FeedRefreshRuntimeSettings:
    try:
        with SessionLocal() as session:
            user = get_primary_user(session)
            setting = next(
                (
                    item
                    for item in user.integration_settings
                    if item.integration_key == FEED_REFRESH_SETTINGS_KEY
                ),
                None,
            )
            if setting is None:
                return _default_feed_refresh_runtime_settings()
            return _runtime_from_feed_refresh_config(
                dict(setting.config or {}),
                bool(setting.is_enabled),
            )
    except SQLAlchemyError:
        seed_store()
        with STORE.lock:
            record = STORE.integrations.get(FEED_REFRESH_SETTINGS_KEY)
            if record is None:
                return _default_feed_refresh_runtime_settings()
            return _runtime_from_feed_refresh_config(
                dict(record.get("config") or {}),
                bool(record.get("is_enabled", True)),
            )


def get_feed_refresh_settings() -> FeedRefreshSettingsEntry:
    try:
        with SessionLocal() as session:
            user = get_primary_user(session)
            setting = next(
                (
                    item
                    for item in user.integration_settings
                    if item.integration_key == FEED_REFRESH_SETTINGS_KEY
                ),
                None,
            )
            if setting is None:
                return _feed_refresh_entry_from_runtime(_default_feed_refresh_runtime_settings())
            runtime = _runtime_from_feed_refresh_config(
                dict(setting.config or {}),
                bool(setting.is_enabled),
            )
            return _feed_refresh_entry_from_runtime(runtime, setting.updated_at)
    except SQLAlchemyError:
        runtime = get_feed_refresh_runtime_settings()
        record = STORE.integrations.get(FEED_REFRESH_SETTINGS_KEY)
        updated_at = record.get("updated_at") if isinstance(record, dict) else None
        return _feed_refresh_entry_from_runtime(runtime, updated_at)


def update_feed_refresh_settings(
    payload: FeedRefreshSettingsUpdateRequest,
) -> FeedRefreshSettingsEntry:
    runtime = _validate_feed_refresh_settings(
        payload.enabled,
        int(payload.interval_value),
        payload.interval_unit,
    )
    config = {
        "interval_value": runtime.interval_value,
        "interval_unit": runtime.interval_unit,
    }
    now = datetime.now(UTC)
    try:
        with SessionLocal() as session:
            user = get_primary_user(session)
            setting = next(
                (
                    item
                    for item in user.integration_settings
                    if item.integration_key == FEED_REFRESH_SETTINGS_KEY
                ),
                None,
            )
            if setting is None:
                setting = IntegrationSetting(
                    user_id=user.id,
                    integration_key=FEED_REFRESH_SETTINGS_KEY,
                    display_name=FEED_REFRESH_DISPLAY_NAME,
                    is_enabled=runtime.enabled,
                    config=config,
                )
                session.add(setting)
            else:
                setting.display_name = FEED_REFRESH_DISPLAY_NAME
                setting.is_enabled = runtime.enabled
                setting.config = config
            session.commit()
            session.refresh(setting)
            return _feed_refresh_entry_from_runtime(runtime, setting.updated_at)
    except SQLAlchemyError:
        seed_store()
        with STORE.lock:
            STORE.integrations[FEED_REFRESH_SETTINGS_KEY] = {
                "id": FEED_REFRESH_SETTINGS_KEY,
                "integration_key": FEED_REFRESH_SETTINGS_KEY,
                "display_name": FEED_REFRESH_DISPLAY_NAME,
                "is_enabled": runtime.enabled,
                "config": config,
                "updated_at": now,
            }
        return _feed_refresh_entry_from_runtime(runtime, now)


def _parse_cookie_header(raw_cookie: str | None) -> dict[str, str | None]:
    parsed = {field: None for field in COOKIE_KEYS.values()}
    if not raw_cookie or not raw_cookie.strip():
        return parsed

    cookie = SimpleCookie()
    try:
        cookie.load(raw_cookie)
        for source_key, target_key in COOKIE_KEYS.items():
            morsel = cookie.get(source_key)
            if morsel is not None:
                parsed[target_key] = _normalize_secret(morsel.value)
    except Exception:
        pass

    if any(parsed.values()):
        return parsed

    for part in raw_cookie.split(';'):
        if '=' not in part:
            continue
        key, value = part.split('=', 1)
        normalized_key = key.strip()
        target_key = COOKIE_KEYS.get(normalized_key)
        if target_key:
            parsed[target_key] = _normalize_secret(value)
    return parsed


def _entry_from_values(
    *,
    is_enabled: bool,
    values: dict[str, Any],
    updated_at: datetime | None,
) -> BilibiliIntegrationSettingsEntry:
    sessdata = values.get('sessdata')
    bili_jct = values.get('bili_jct')
    buvid3 = values.get('buvid3')
    has_cookie_values = any((sessdata, bili_jct, buvid3))
    ready = is_enabled and bool(sessdata and bili_jct)
    return BilibiliIntegrationSettingsEntry(
        is_enabled=is_enabled,
        has_cookie_values=has_cookie_values,
        ready_for_authenticated_fetch=ready,
        sessdata_configured=bool(sessdata),
        sessdata_preview=_mask_secret(sessdata),
        bili_jct_configured=bool(bili_jct),
        bili_jct_preview=_mask_secret(bili_jct),
        buvid3_configured=bool(buvid3),
        buvid3_preview=_mask_secret(buvid3),
        updated_at=updated_at,
    )


def _store_record_from_entry(
    entry: BilibiliIntegrationSettingsEntry,
    values: dict[str, Any],
) -> dict[str, Any]:
    return {
        'id': entry.integration_key,
        'integration_key': entry.integration_key,
        'display_name': entry.display_name,
        'is_enabled': entry.is_enabled,
        'config': dict(values),
        'updated_at': entry.updated_at or datetime.now(UTC),
    }


def get_bilibili_integration_settings() -> BilibiliIntegrationSettingsEntry:
    try:
        with SessionLocal() as session:
            setting = get_bilibili_integration_setting(session)
            if setting is None:
                return _entry_from_values(is_enabled=False, values={}, updated_at=None)
            values = dict(setting.config or {})
            return _entry_from_values(
                is_enabled=bool(setting.is_enabled),
                values=values,
                updated_at=setting.updated_at,
            )
    except SQLAlchemyError:
        seed_store()
        with STORE.lock:
            record = STORE.integrations.get(BILIBILI_INTEGRATION_KEY)
            if record is None:
                return _entry_from_values(is_enabled=False, values={}, updated_at=None)
            return _entry_from_values(
                is_enabled=bool(record.get('is_enabled')),
                values=dict(record.get('config') or {}),
                updated_at=record.get('updated_at'),
            )


def update_bilibili_integration_settings(
    payload: BilibiliIntegrationSettingsUpdateRequest,
) -> BilibiliIntegrationSettingsEntry:
    parsed_cookie = _parse_cookie_header(payload.cookie_header)
    now = datetime.now(UTC)

    try:
        with SessionLocal() as session:
            setting = get_bilibili_integration_setting(session)
            existing_values = dict(setting.config or {}) if setting is not None else {}
            resolved_values = dict(existing_values)
            for key, value in parsed_cookie.items():
                if value:
                    resolved_values[key] = value
            explicit_updates = {
                'sessdata': payload.sessdata,
                'bili_jct': payload.bili_jct,
                'buvid3': payload.buvid3,
            }
            for key, raw_value in explicit_updates.items():
                if raw_value is None:
                    continue
                resolved_values[key] = _normalize_secret(raw_value)
            if setting is None:
                user = get_primary_user(session)
                setting = IntegrationSetting(
                    user_id=user.id,
                    integration_key=BILIBILI_INTEGRATION_KEY,
                    display_name=BILIBILI_DISPLAY_NAME,
                    is_enabled=payload.is_enabled,
                    config=resolved_values,
                )
                session.add(setting)
            else:
                setting.display_name = BILIBILI_DISPLAY_NAME
                setting.is_enabled = payload.is_enabled
                setting.config = resolved_values
            session.commit()
            session.refresh(setting)
            return _entry_from_values(
                is_enabled=bool(setting.is_enabled),
                values=dict(setting.config or {}),
                updated_at=setting.updated_at,
            )
    except SQLAlchemyError:
        seed_store()
        with STORE.lock:
            existing_record = STORE.integrations.get(BILIBILI_INTEGRATION_KEY) or {}
            resolved_values = dict(existing_record.get('config') or {})
            for key, value in parsed_cookie.items():
                if value:
                    resolved_values[key] = value
            explicit_updates = {
                'sessdata': payload.sessdata,
                'bili_jct': payload.bili_jct,
                'buvid3': payload.buvid3,
            }
            for key, raw_value in explicit_updates.items():
                if raw_value is None:
                    continue
                resolved_values[key] = _normalize_secret(raw_value)
            entry = _entry_from_values(
                is_enabled=payload.is_enabled,
                values=resolved_values,
                updated_at=now,
            )
            STORE.integrations[BILIBILI_INTEGRATION_KEY] = _store_record_from_entry(
                entry,
                resolved_values,
            )
        return entry


def parse_bilibili_cookie_header(raw_cookie: str | None) -> BilibiliIntegrationCookieParseResponse:
    values = _parse_cookie_header(raw_cookie)
    extracted = {
        key: IntegrationSecretStatus(configured=bool(value), preview=_mask_secret(value))
        for key, value in values.items()
    }
    return BilibiliIntegrationCookieParseResponse(
        extracted=extracted,
        extracted_count=sum(1 for value in values.values() if value),
    )
