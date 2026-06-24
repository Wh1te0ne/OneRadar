from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata as importlib_metadata
from typing import Any

from app.core.config import get_settings

SUPPORTED_SOCIAL_PLATFORMS = {"douyin", "xiaohongshu"}

SOURCE_NAMES = {
    "douyin": "抖音",
    "xiaohongshu": "小红书",
}


@dataclass(frozen=True)
class SocialPlatformPreview:
    final_url: str | None
    platform: str
    content_type: str
    title: str
    source_name: str
    author: str | None
    published_at: datetime | None
    original_text: str
    source_text_kind: str
    metadata: dict[str, object]
    fetched_at: datetime


def preview_social_platform_url(url: str, platform: str) -> SocialPlatformPreview:
    if platform not in SUPPORTED_SOCIAL_PLATFORMS:
        raise ValueError(f"{platform} 临时分析适配器尚未接入；当前不会把链接保存为阅读条目。")

    try:
        from parsehub import ParseHub
        from parsehub.errors import ParseError, UnknownPlatform
    except ImportError as exc:
        raise ValueError("平台解析库 parsehub 未安装，暂时无法分析该平台链接。") from exc

    settings = get_settings()
    cookie = _cookie_for_platform(platform)
    proxy = _clean_setting(settings.social_parse_proxy)

    try:
        result = ParseHub().parse_sync(url, cookie=cookie, proxy=proxy)
    except UnknownPlatform as exc:
        raise ValueError(f"{SOURCE_NAMES[platform]} 链接暂不支持解析。") from exc
    except ParseError as exc:
        raise ValueError(f"{SOURCE_NAMES[platform]} 链接解析失败：{exc}") from exc
    except Exception as exc:
        message = f"{SOURCE_NAMES[platform]} 链接解析失败，请稍后重试或配置平台 Cookie。"
        raise ValueError(message) from exc

    title = _clean_text(getattr(result, "title", None)) or f"{SOURCE_NAMES[platform]}内容"
    content = _clean_text(
        getattr(result, "markdown_content", None) or getattr(result, "content", None)
    )
    original_text = _join_text([title, content])
    media = _normalize_media(getattr(result, "media", None))

    metadata: dict[str, object] = {
        "parser_name": "parsehub",
        "parser_version": _parsehub_version(),
        "raw_url": _clean_text(getattr(result, "raw_url", None)),
        "media_count": len(media),
        "media": media,
    }
    parser_platform = getattr(result, "platform", None)
    if parser_platform is not None:
        metadata["parser_platform"] = str(parser_platform)

    return SocialPlatformPreview(
        final_url=_clean_text(getattr(result, "raw_url", None)) or url,
        platform=platform,
        content_type=_content_type(result),
        title=title,
        source_name=SOURCE_NAMES[platform],
        author=None,
        published_at=None,
        original_text=original_text,
        source_text_kind="platform_visible_text",
        metadata=metadata,
        fetched_at=datetime.now(UTC),
    )


def _cookie_for_platform(platform: str) -> str | None:
    settings = get_settings()
    if platform == "douyin":
        return _clean_setting(settings.douyin_cookie)
    if platform == "xiaohongshu":
        return _clean_setting(settings.xiaohongshu_cookie)
    return None


def _clean_setting(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _join_text(parts: list[str]) -> str:
    visible = [part for part in parts if part]
    if not visible:
        return "未提取到平台可见正文。"
    return "\n\n".join(visible)


def _content_type(result: object) -> str:
    class_name = type(result).__name__.lower()
    if "video" in class_name:
        return "video"
    if "image" in class_name:
        return "image"
    if "multimedia" in class_name:
        return "multimedia"
    if "richtext" in class_name:
        return "article"
    return "platform"


def _normalize_media(value: object) -> list[dict[str, object]]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple, set)):
        items = [value]
    else:
        items = list(value)
    return [_serialize_media_item(item) for item in items if item is not None]


def _serialize_media_item(item: object) -> dict[str, object]:
    if isinstance(item, str):
        return {"url": item}
    data = getattr(item, "__dict__", {})
    if not isinstance(data, dict):
        return {"value": str(item)}
    fields = {
        key: _serialize_metadata_value(value)
        for key, value in data.items()
        if not key.startswith("_") and value not in (None, "")
    }
    if fields:
        return fields
    return {"value": str(item)}


def _serialize_metadata_value(value: Any) -> object:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (list, tuple, set)):
        return [_serialize_metadata_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize_metadata_value(item) for key, item in value.items()}
    data = getattr(value, "__dict__", None)
    if isinstance(data, dict):
        return {
            str(key): _serialize_metadata_value(item)
            for key, item in data.items()
            if not str(key).startswith("_")
        }
    return str(value)


def _parsehub_version() -> str | None:
    try:
        return importlib_metadata.version("parsehub")
    except importlib_metadata.PackageNotFoundError:
        return None
