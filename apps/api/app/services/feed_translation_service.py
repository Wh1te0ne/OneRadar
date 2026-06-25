from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import FeedEntry
from app.db.session import SessionLocal
from app.services.provider_registry import ProviderCapability, resolve_provider_config

logger = logging.getLogger(__name__)

BATCH_SIZE = 20
SUMMARY_CHAR_LIMIT = 800
TRANSLATION_TARGET_LANGUAGE = "zh-CN"


@dataclass(frozen=True, slots=True)
class FeedTranslationResult:
    total: int = 0
    translated: int = 0
    skipped: int = 0
    failed: int = 0


def feed_translation_source_hash(title: str, summary: str | None) -> str:
    source = json.dumps(
        {"title": title.strip(), "summary": (summary or "").strip()},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def display_feed_title(title: str, translated_title: str | None) -> str:
    cleaned_title = title.strip()
    cleaned_translation = (translated_title or "").strip()
    if not cleaned_translation or cleaned_translation == cleaned_title:
        return cleaned_title
    return f"{cleaned_translation} ---> {cleaned_title}"


def display_feed_summary(summary: str | None, translated_summary: str | None) -> str | None:
    return (translated_summary or summary or "").strip() or None


def translate_feed_entries(
    *,
    entry_ids: list[UUID] | None = None,
    user_id: object | None = None,
    published_since: datetime | None = None,
    limit: int = 200,
) -> FeedTranslationResult:
    entries = _translation_candidates(
        entry_ids=entry_ids,
        user_id=user_id,
        published_since=published_since,
        limit=limit,
    )
    if not entries:
        return FeedTranslationResult()

    skipped = _mark_chinese_entries_skipped(entries)
    pending = [entry for entry in entries if not _looks_chinese(_entry_source_text(entry))]
    if not pending:
        return FeedTranslationResult(total=len(entries), skipped=skipped)

    try:
        provider = resolve_provider_config(None, ProviderCapability.summarization)
        if not provider.base_url or not provider.api_key or not provider.model_name:
            return FeedTranslationResult(total=len(entries), skipped=skipped, failed=len(pending))
    except ValueError:
        return FeedTranslationResult(total=len(entries), skipped=skipped, failed=len(pending))

    translated = 0
    failed = 0
    for batch in _chunks(pending, BATCH_SIZE):
        try:
            translations = _translate_batch(batch, provider)
            translated += _apply_translations(batch, translations, provider)
            failed += max(0, len(batch) - len(translations))
        except Exception as exc:
            logger.exception("RSS feed translation batch failed")
            failed += len(batch)
            _mark_entries_failed(batch, str(exc))
    return FeedTranslationResult(
        total=len(entries),
        translated=translated,
        skipped=skipped,
        failed=failed,
    )


def _translation_candidates(
    *,
    entry_ids: list[UUID] | None,
    user_id: object | None,
    published_since: datetime | None,
    limit: int,
) -> list[FeedEntry]:
    try:
        with SessionLocal() as session:
            query = select(FeedEntry)
            if entry_ids is not None:
                if not entry_ids:
                    return []
                query = query.where(FeedEntry.id.in_(entry_ids))
            else:
                query = query.where(
                    (FeedEntry.translation_status.is_(None))
                    | (FeedEntry.translation_status.in_(["pending", "failed"]))
                )
                if user_id is not None:
                    query = query.where(FeedEntry.user_id == user_id)
                if published_since is not None:
                    query = query.where(FeedEntry.published_at >= published_since)
            query = query.order_by(FeedEntry.published_at.desc().nullslast())
            if entry_ids is None:
                query = query.limit(max(1, limit))
            rows = list(session.execute(query).scalars().all())
            for entry in rows:
                session.expunge(entry)
            return rows
    except SQLAlchemyError:
        return []


def _mark_chinese_entries_skipped(entries: list[FeedEntry]) -> int:
    chinese_entries = [entry for entry in entries if _looks_chinese(_entry_source_text(entry))]
    if not chinese_entries:
        return 0
    try:
        with SessionLocal() as session:
            for entry in chinese_entries:
                current = session.get(FeedEntry, entry.id)
                if current is None:
                    continue
                current.translation_status = "skipped"
                current.translation_language = TRANSLATION_TARGET_LANGUAGE
                current.translation_source_hash = feed_translation_source_hash(
                    current.title,
                    current.summary,
                )
                current.translation_error = None
            session.commit()
    except SQLAlchemyError:
        return 0
    return len(chinese_entries)


def _translate_batch(entries: list[FeedEntry], provider) -> dict[str, dict[str, str]]:
    from app.services.daily_news_service import _call_chat_completion

    payload = [
        {
            "id": str(entry.id),
            "title": entry.title.strip(),
            "summary": (entry.summary or "").strip()[:SUMMARY_CHAR_LIMIT],
        }
        for entry in entries
    ]
    prompt = (
        "你是 OneRadar 的 RSS 新闻翻译器。请把每条新闻的 title 和 summary 翻译成简体中文。\n"
        "要求：\n"
        "1. 只翻译，不总结，不添加原文没有的信息。\n"
        "2. 专有名词、公司名、产品名可保留英文。\n"
        "3. summary 为空时返回空字符串。\n"
        "4. 只返回 JSON 对象，格式为："
        '{"items":[{"id":"...","translated_title":"...","translated_summary":"..."}]}\n\n'
        f"待翻译内容：\n{json.dumps({'items': payload}, ensure_ascii=False)}"
    )
    raw = _call_chat_completion(
        base_url=provider.base_url,
        api_key=provider.api_key,
        model_name=provider.model_name,
        provider_type=provider.provider_type,
        provider_config=provider.provider_config,
        prompt=prompt,
    )
    parsed = _parse_translation_json(raw)
    items = parsed.get("items") if isinstance(parsed, dict) else None
    if not isinstance(items, list):
        raise ValueError("translation response missing items")
    translations: dict[str, dict[str, str]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        entry_id = str(item.get("id") or "").strip()
        if not entry_id:
            continue
        translations[entry_id] = {
            "translated_title": str(item.get("translated_title") or "").strip(),
            "translated_summary": str(item.get("translated_summary") or "").strip(),
        }
    return translations


def _apply_translations(
    entries: list[FeedEntry],
    translations: dict[str, dict[str, str]],
    provider,
) -> int:
    translated = 0
    now = datetime.now(UTC)
    with SessionLocal() as session:
        for entry in entries:
            item = translations.get(str(entry.id))
            current = session.get(FeedEntry, entry.id)
            if current is None:
                continue
            if not item:
                current.translation_status = "failed"
                current.translation_error = "translation response omitted entry"
                continue
            current.translated_title = item["translated_title"] or None
            current.translated_summary = item["translated_summary"] or None
            current.translation_language = TRANSLATION_TARGET_LANGUAGE
            current.translation_provider = provider.provider_name
            current.translation_model = provider.model_name
            current.translation_status = "done"
            current.translation_error = None
            current.translation_source_hash = feed_translation_source_hash(
                current.title,
                current.summary,
            )
            current.translated_at = now
            translated += 1
        session.commit()
    return translated


def _mark_entries_failed(entries: list[FeedEntry], error: str) -> None:
    try:
        with SessionLocal() as session:
            for entry in entries:
                current = session.get(FeedEntry, entry.id)
                if current is None:
                    continue
                current.translation_status = "failed"
                current.translation_error = error[:500]
            session.commit()
    except SQLAlchemyError:
        pass


def _entry_source_text(entry: FeedEntry) -> str:
    return "\n".join(part for part in [entry.title, entry.summary or ""] if part.strip())


def _looks_chinese(text: str) -> bool:
    cleaned = text.strip()
    if not cleaned:
        return True
    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", cleaned))
    alpha_count = len(re.findall(r"[A-Za-z]", cleaned))
    return cjk_count >= 4 and cjk_count >= alpha_count * 0.25


def _chunks(entries: list[FeedEntry], size: int) -> list[list[FeedEntry]]:
    return [entries[index : index + size] for index in range(0, len(entries), size)]


def _parse_translation_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise
