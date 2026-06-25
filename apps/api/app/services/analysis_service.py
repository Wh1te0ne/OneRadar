from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import urlsplit

from fastapi import HTTPException

from app.schemas.analysis import AnalysisSummary, SourceMaterial, UrlAnalysisResponse
from app.services.daily_news_service import _call_chat_completion
from app.services.feed_service import preview_feed_article
from app.services.items_service import preview_bilibili_item
from app.services.provider_registry import ProviderCapability, resolve_provider_config
from app.services.social_platform_service import preview_social_platform_url

PLATFORM_HOST_SUFFIXES = {
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "douyin.com": "douyin",
    "iesdouyin.com": "douyin",
    "xiaohongshu.com": "xiaohongshu",
    "xhslink.com": "xiaohongshu",
}


def _platform_from_url(url: str, hint: str | None = None) -> str:
    normalized_hint = (hint or "").strip().lower()
    if normalized_hint:
        return normalized_hint
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return "web"
    if (
        host == "b23.tv"
        or host.endswith(".b23.tv")
        or host == "bilibili.com"
        or host.endswith(".bilibili.com")
    ):
        return "bilibili"
    if host == "mp.weixin.qq.com":
        return "wechat"
    for suffix, platform in PLATFORM_HOST_SUFFIXES.items():
        if host == suffix or host.endswith("." + suffix):
            return platform
    return "web"


def _extractive_summary(text: str, limit: int = 520) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= limit:
        return cleaned
    boundary = max(
        cleaned.rfind("。", 0, limit),
        cleaned.rfind(".", 0, limit),
        cleaned.rfind("！", 0, limit),
        cleaned.rfind("？", 0, limit),
    )
    if boundary >= 80:
        return cleaned[: boundary + 1]
    return cleaned[:limit].rstrip() + "..."


def _model_summary(title: str, source_text: str) -> tuple[str, str, str | None]:
    try:
        provider = resolve_provider_config(None, ProviderCapability.summarization)
    except ValueError:
        return _extractive_summary(source_text), "extractive", None
    if not provider.base_url or not provider.api_key or not provider.model_name:
        return _extractive_summary(source_text), "extractive", None

    source_excerpt = source_text[:12000]
    prompt = (
        "你是 OneRadar 的临时链接分析器。请基于下面的原文或平台简介，输出中文摘要。\n"
        "要求：\n"
        "1. 不要编造原文没有的信息。\n"
        "2. 用 3 到 6 条要点概括核心内容。\n"
        "3. 如果材料不足，明确说明只能基于当前可见文本判断。\n\n"
        f"标题：{title}\n\n"
        f"材料：\n{source_excerpt}"
    )
    try:
        return (
            _call_chat_completion(
                base_url=provider.base_url,
                api_key=provider.api_key,
                model_name=provider.model_name,
                provider_type=provider.provider_type,
                provider_config=provider.provider_config,
                prompt=prompt,
            ).strip(),
            provider.provider_name,
            provider.model_name,
        )
    except HTTPException:
        raise
    except Exception:
        return _extractive_summary(source_text), "extractive", None


def _source_material_kind(platform: str, content_type: str, source_text_kind: str) -> str:
    if source_text_kind == "readable_text":
        return "article_text"
    if platform == "bilibili":
        return "metadata_description"
    if content_type in {"video", "image", "multimedia", "note", "platform"}:
        return "caption_plus_media"
    return source_text_kind


def _source_completeness(platform: str, source_text_kind: str, metadata: dict[str, object]) -> str:
    if source_text_kind == "readable_text":
        return "full"
    if platform == "bilibili" and metadata.get("subtitle_status") not in {"ok", "available"}:
        return "metadata_only"
    return "partial"


def _source_warnings(platform: str, completeness: str, metadata: dict[str, object]) -> list[str]:
    if completeness == "full":
        return []
    if platform == "bilibili":
        return ["未获取到完整字幕；原始材料基于视频标题、简介和可见元数据。"]
    if platform in {"douyin", "xiaohongshu"}:
        media_count = int(metadata.get("media_count") or 0)
        if media_count:
            return ["未下载或持久化媒体；原始材料基于平台可见文本和媒体元数据。"]
        return ["未获取到完整媒体内容；原始材料基于平台可见文本。"]
    return ["原始材料不是完整正文；总结仅基于当前可解析内容。"]


def _source_assets(metadata: dict[str, object]) -> list[dict[str, object]]:
    media = metadata.get("media")
    if not isinstance(media, list):
        return []
    assets = []
    for index, item in enumerate(media, start=1):
        if isinstance(item, dict):
            assets.append({"index": index, "metadata": item})
        else:
            assets.append({"index": index, "metadata": {"value": str(item)}})
    return assets


def _source_markdown(
    *,
    title: str,
    source_url: str,
    final_url: str | None,
    platform: str,
    content_type: str,
    source_name: str | None,
    author: str | None,
    source_text_kind: str,
    completeness: str,
    warnings: list[str],
    text: str,
) -> str:
    lines = [
        f"# {title}",
        "",
        f"> 来源：{final_url or source_url}",
        f"> 平台：{source_name or platform}",
        f"> 类型：{content_type}",
        f"> 材料类型：{source_text_kind}",
        f"> 完整度：{completeness}",
    ]
    if author:
        lines.append(f"> 作者：{author}")
    if warnings:
        lines.extend(["", "## 解析提示", *[f"- {warning}" for warning in warnings]])
    lines.extend(["", "## 原始材料", "", text.strip()])
    return "\n".join(lines).strip()


def _summary_markdown(summary: str) -> str:
    return "\n".join(["## AI 总结", "", summary.strip()]).strip()


def _key_points(summary: str) -> list[str]:
    points = []
    for line in summary.splitlines():
        cleaned = line.strip().lstrip("-•0123456789.、) ").strip()
        if cleaned:
            points.append(cleaned)
    return points[:12]


def _analysis_response(
    *,
    source_url: str,
    final_url: str | None,
    platform: str,
    content_type: str,
    title: str,
    source_name: str | None,
    author: str | None,
    published_at,
    original_text: str,
    source_text_kind: str,
    summary: str,
    summary_provider: str,
    model_name: str | None,
    metadata: dict[str, object],
    fetched_at: datetime,
) -> UrlAnalysisResponse:
    completeness = _source_completeness(platform, source_text_kind, metadata)
    warnings = _source_warnings(platform, completeness, metadata)
    source_markdown = _source_markdown(
        title=title,
        source_url=source_url,
        final_url=final_url,
        platform=platform,
        content_type=content_type,
        source_name=source_name,
        author=author,
        source_text_kind=source_text_kind,
        completeness=completeness,
        warnings=warnings,
        text=original_text,
    )
    summary_markdown = _summary_markdown(summary)
    return UrlAnalysisResponse(
        source_url=source_url,
        final_url=final_url,
        platform=platform,
        content_type=content_type,
        title=title,
        source_name=source_name,
        author=author,
        published_at=published_at,
        original_text=original_text,
        source_text_kind=source_text_kind,
        summary=summary,
        source_material=SourceMaterial(
            kind=_source_material_kind(platform, content_type, source_text_kind),
            text=original_text,
            markdown=source_markdown,
            assets=_source_assets(metadata),
            completeness=completeness,
            warnings=warnings,
        ),
        ai_summary=AnalysisSummary(
            summary=summary,
            markdown=summary_markdown,
            key_points=_key_points(summary),
            provider=summary_provider,
            model_name=model_name,
        ),
        source_markdown=source_markdown,
        summary_markdown=summary_markdown,
        summary_provider=summary_provider,
        model_name=model_name,
        metadata=metadata,
        fetched_at=fetched_at,
        persisted=False,
    )


def analyze_url(url: str, platform_hint: str | None = None) -> UrlAnalysisResponse:
    source_url = url.strip()
    if not source_url:
        raise ValueError("url is required")
    platform = _platform_from_url(source_url, platform_hint)

    if platform == "bilibili":
        preview = preview_bilibili_item(source_url)
        original_text = (
            preview.description or f"{preview.title}\nUP 主：{preview.owner_name or '未知'}"
        )
        summary, summary_provider, model_name = _model_summary(preview.title, original_text)
        return _analysis_response(
            source_url=source_url,
            final_url=preview.normalized_url,
            platform="bilibili",
            content_type="video",
            title=preview.title,
            source_name="Bilibili",
            author=preview.owner_name,
            published_at=preview.published_at,
            original_text=original_text,
            source_text_kind="metadata_description",
            summary=summary,
            summary_provider=summary_provider,
            model_name=model_name,
            metadata={
                "bvid": preview.bvid,
                "aid": preview.aid,
                "cid": preview.cid,
                "duration_seconds": preview.duration_seconds,
                "duration_text": preview.duration_text,
                "cover_url": preview.cover_url,
                "page_count": preview.page_count,
                "subtitle_status": preview.subtitle_status,
            },
            fetched_at=datetime.now(UTC),
        )

    if platform in {"douyin", "xiaohongshu"}:
        preview = preview_social_platform_url(source_url, platform)
        summary, summary_provider, model_name = _model_summary(preview.title, preview.original_text)
        return _analysis_response(
            source_url=source_url,
            final_url=preview.final_url,
            platform=preview.platform,
            content_type=preview.content_type,
            title=preview.title,
            source_name=preview.source_name,
            author=preview.author,
            published_at=preview.published_at,
            original_text=preview.original_text,
            source_text_kind=preview.source_text_kind,
            summary=summary,
            summary_provider=summary_provider,
            model_name=model_name,
            metadata=preview.metadata,
            fetched_at=preview.fetched_at,
        )

    if platform == "youtube":
        raise ValueError(f"{platform} 临时分析适配器尚未接入；当前不会把链接保存为阅读条目。")

    article = preview_feed_article(source_url)
    summary, summary_provider, model_name = _model_summary(article.title, article.plain_text)
    return _analysis_response(
        source_url=source_url,
        final_url=article.final_url,
        platform=platform,
        content_type="article",
        title=article.title,
        source_name=article.site_title,
        author=article.author,
        published_at=article.published_at,
        original_text=article.plain_text,
        source_text_kind="readable_text",
        summary=summary,
        summary_provider=summary_provider,
        model_name=model_name,
        metadata={
            "parser_name": article.parser_name,
            "parser_version": article.parser_version,
            "feed_summary": article.summary,
        },
        fetched_at=article.fetched_at,
    )
