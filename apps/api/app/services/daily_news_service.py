from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import DailyNewsReport
from app.db.session import SessionLocal
from app.schemas.daily_news import (
    DailyNewsGenerateRequest,
    DailyNewsLead,
    DailyNewsReportResponse,
    DailyNewsSection,
)
from app.services.db_access import get_primary_user
from app.services.feed_state_service import get_feed_state
from app.services.provider_registry import ProviderCapability, resolve_provider_config
from app.services.store import STORE, seed_store

DAILY_NEWS_TIMEZONE = ZoneInfo("Asia/Shanghai")
DEFAULT_FRESHNESS_HOURS = 24
MAX_REPORT_ENTRIES = 60


def today_report_date() -> str:
    return datetime.now(DAILY_NEWS_TIMEZONE).date().isoformat()


def get_daily_news(report_date: str | None = None) -> DailyNewsReportResponse:
    normalized_date = _normalize_report_date(report_date)
    record = _get_report_record(normalized_date)
    if record is None:
        return DailyNewsReportResponse(report_date=normalized_date, status="missing")
    return _response_from_record(record)


def generate_daily_news(payload: DailyNewsGenerateRequest) -> DailyNewsReportResponse:
    report_date = _normalize_report_date(payload.date)
    existing = _get_report_record(report_date)
    if existing is not None and not payload.force:
        raise HTTPException(status_code=409, detail="当日新闻日报已存在，重新生成会覆盖当前版本。")

    entries = _fresh_entries_for_report(report_date)
    if not entries:
        record = {
            "report_date": report_date,
            "status": "ready",
            "headline": "今日没有可生成日报的新内容",
            "lead": None,
            "sections": [],
            "source_entries": [],
            "raw_model_output": None,
            "provider_name": None,
            "model_name": None,
            "entry_count": 0,
            "freshness_hours": DEFAULT_FRESHNESS_HOURS,
            "generated_at": datetime.now(UTC),
            "error_message": None,
        }
        return _response_from_record(_save_report_record(record))

    generated = _generate_report_payload(entries, report_date)
    source_entries = [_public_entry(entry) for entry in entries]
    record = {
        "report_date": report_date,
        "status": "ready",
        "headline": str(generated.get("headline") or "每日新闻").strip() or "每日新闻",
        "lead": _normalize_item(generated.get("lead"), entries),
        "sections": _normalize_sections(generated.get("sections"), entries),
        "source_entries": source_entries,
        "raw_model_output": generated.get("raw_model_output"),
        "provider_name": generated.get("provider_name"),
        "model_name": generated.get("model_name"),
        "entry_count": len(entries),
        "freshness_hours": DEFAULT_FRESHNESS_HOURS,
        "generated_at": datetime.now(UTC),
        "error_message": None,
    }
    return _response_from_record(_save_report_record(record))


def generate_today_if_missing() -> DailyNewsReportResponse | None:
    report_date = today_report_date()
    if _get_report_record(report_date) is not None:
        return None
    return generate_daily_news(DailyNewsGenerateRequest(date=report_date, force=False))


def _normalize_report_date(value: str | None) -> str:
    if not value:
        return today_report_date()
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as error:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD") from error


def _daily_news_reference_time() -> datetime:
    return datetime.now(DAILY_NEWS_TIMEZONE)


def _fresh_entries_for_report(report_date: str) -> list[dict[str, Any]]:
    _ = date.fromisoformat(report_date)
    end = _daily_news_reference_time()
    start = end - timedelta(hours=24)
    state = get_feed_state()
    entries: list[dict[str, Any]] = []
    ordinal = 1
    for feed in state.feeds.values():
        for item in feed.items:
            if item.published_at is None:
                continue
            published = item.published_at.astimezone(DAILY_NEWS_TIMEZONE)
            if published < start or published > end:
                continue
            entries.append(
                {
                    "id": f"n{ordinal}",
                    "original_id": item.id,
                    "title": item.title,
                    "link": item.link,
                    "summary": item.summary,
                    "author": item.author,
                    "published_at": item.published_at,
                    "tags": item.tags,
                    "source_url": feed.source_url,
                    "source_title": feed.site_title,
                }
            )
            ordinal += 1
    entries.sort(
        key=lambda entry: entry.get("published_at") or datetime.fromtimestamp(0, tz=UTC),
        reverse=True,
    )
    return entries[:MAX_REPORT_ENTRIES]


def _generate_report_payload(entries: list[dict[str, Any]], report_date: str) -> dict[str, Any]:
    try:
        provider = resolve_provider_config(None, ProviderCapability.summarization)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="日报生成需要先配置当前使用的大语言模型。",
        ) from exc
    if not provider.base_url:
        raise HTTPException(status_code=400, detail="日报生成需要先配置大语言模型 BaseURL。")
    if not provider.api_key:
        raise HTTPException(status_code=400, detail="日报生成需要先配置可用的大语言模型 API Key。")
    if not provider.model_name:
        raise HTTPException(status_code=400, detail="日报生成需要先配置摘要/聊天模型。")
    raw_output = _call_chat_completion(
        base_url=provider.base_url,
        api_key=provider.api_key,
        model_name=provider.model_name,
        prompt=_daily_news_prompt(entries, report_date),
    )
    parsed = _parse_model_json(raw_output)
    parsed["raw_model_output"] = raw_output
    parsed["provider_name"] = provider.provider_name
    parsed["model_name"] = provider.model_name
    return parsed


def _call_chat_completion(
    *,
    base_url: str | None,
    api_key: str,
    model_name: str,
    prompt: str,
) -> str:
    endpoint = _chat_endpoint(base_url)
    request = Request(
        endpoint,
        data=json.dumps(
            {
                "model": model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                "temperature": 0.25,
                "max_tokens": 3800,
            }
        ).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=160) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError) as error:
        raise HTTPException(status_code=502, detail=f"日报模型调用失败：{error}") from error
    text = _extract_chat_text(payload)
    if not text:
        raise HTTPException(status_code=502, detail="日报模型返回为空。")
    return text


def _daily_news_prompt(entries: list[dict[str, Any]], report_date: str) -> str:
    source_lines = []
    for entry in entries:
        source_lines.append(
            json.dumps(
                {
                    "id": entry["id"],
                    "source": entry["source_title"],
                    "published_at": _iso(entry.get("published_at")),
                    "title": entry["title"],
                    "summary": entry.get("summary") or "",
                    "tags": entry.get("tags") or [],
                },
                ensure_ascii=False,
            )
        )
    return (
        "你是 OneRadar 的中文新闻日报编辑。请根据 RSS 条目生成一份固定结构的中文每日新闻页。\n"
        "要求：\n"
        "1. 必须该翻译就翻译，该总结就总结，不能只复制原始英文标题。\n"
        "2. lead 必须选择当天最重头、影响最大、最值得优先阅读的一条新闻，"
        "而不是最新的一条。必须返回它的 entry_id。\n"
        "3. sections 做 3 到 5 个主题，每个主题包含 summary 和 2 到 5 条 item。"
        "主题标题应像新闻专题，例如“大模型技术进展”。\n"
        "4. 每条 item 也必须返回 entry_id，并给出中文 title 与一到两句 summary。\n"
        "5. 不要编造条目外的信息；如果原始摘要不足，只做保守概括。\n"
        "6. 只输出 JSON，不要 Markdown，不要代码围栏。\n"
        "JSON 结构："
        '{"headline":"...","lead":{"title":"...","summary":"...","entry_id":"n1"},'
        '"sections":[{"title":"...","summary":"...","items":[{"title":"...","summary":"...","entry_id":"n2"}]}]}\n'
        f"日报日期：{report_date}\n"
        "RSS 条目：\n"
        + "\n".join(source_lines)
    )


def _parse_model_json(raw_output: str) -> dict[str, Any]:
    text = raw_output.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=502, detail="日报模型没有返回可解析的 JSON。") from error
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="日报模型返回结构不正确。")
    return payload


def _normalize_item(value: Any, entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    entry_id = str(value.get("entry_id") or "").strip()
    entry = _entry_by_id(entries, entry_id) or (entries[0] if entries else None)
    fallback_title = str(entry.get("title") if entry else "今日重点")
    fallback_summary = str(entry.get("summary") or "" if entry else "")
    return {
        "title": str(value.get("title") or fallback_title).strip(),
        "summary": str(value.get("summary") or fallback_summary).strip(),
        "entry_id": entry.get("id") if entry else entry_id or None,
        "entry": _public_entry(entry) if entry else None,
    }


def _normalize_sections(value: Any, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    sections: list[dict[str, Any]] = []
    for section in value[:6]:
        if not isinstance(section, dict):
            continue
        items = [
            _normalize_item(item, entries)
            for item in section.get("items", [])
            if isinstance(item, dict)
        ]
        sections.append(
            {
                "title": str(section.get("title") or "今日速览").strip(),
                "summary": str(section.get("summary") or "").strip(),
                "items": [item for item in items if item is not None],
            }
        )
    return sections


def _entry_by_id(entries: list[dict[str, Any]], entry_id: str) -> dict[str, Any] | None:
    return next((entry for entry in entries if entry.get("id") == entry_id), None)


def _public_entry(entry: dict[str, Any] | None) -> dict[str, Any] | None:
    if entry is None:
        return None
    return {
        "id": str(entry["id"]),
        "title": str(entry["title"]),
        "link": str(entry["link"]),
        "summary": entry.get("summary"),
        "author": entry.get("author"),
        "published_at": _iso(entry.get("published_at")),
        "source_url": str(entry["source_url"]),
        "source_title": str(entry["source_title"]),
    }


def _save_report_record(record: dict[str, Any]) -> dict[str, Any] | DailyNewsReport:
    try:
        with SessionLocal() as session:
            user = get_primary_user(session)
            existing = session.execute(
                select(DailyNewsReport).where(
                    DailyNewsReport.user_id == user.id,
                    DailyNewsReport.report_date == record["report_date"],
                )
            ).scalar_one_or_none()
            if existing is None:
                existing = DailyNewsReport(user_id=user.id, **record)
                session.add(existing)
            else:
                for key, value in record.items():
                    setattr(existing, key, value)
            session.commit()
            session.refresh(existing)
            return existing
    except SQLAlchemyError:
        seed_store()
        with STORE.lock:
            STORE.daily_reports[str(record["report_date"])] = record
        return record


def _get_report_record(report_date: str) -> dict[str, Any] | DailyNewsReport | None:
    try:
        with SessionLocal() as session:
            user = get_primary_user(session)
            return session.execute(
                select(DailyNewsReport).where(
                    DailyNewsReport.user_id == user.id,
                    DailyNewsReport.report_date == report_date,
                )
            ).scalar_one_or_none()
    except SQLAlchemyError:
        seed_store()
        return STORE.daily_reports.get(report_date)


def _response_from_record(record: dict[str, Any] | DailyNewsReport) -> DailyNewsReportResponse:
    if isinstance(record, DailyNewsReport):
        data = {
            "report_date": record.report_date,
            "status": record.status,
            "headline": record.headline,
            "lead": record.lead,
            "sections": record.sections,
            "generated_at": record.generated_at,
            "provider_name": record.provider_name,
            "model_name": record.model_name,
            "entry_count": record.entry_count,
            "freshness_hours": record.freshness_hours,
            "error_message": record.error_message,
        }
    else:
        data = dict(record)
    return DailyNewsReportResponse(
        report_date=str(data["report_date"]),
        status=str(data.get("status") or "ready"),
        headline=data.get("headline"),
        lead=DailyNewsLead.model_validate(data["lead"]) if data.get("lead") else None,
        sections=[
            DailyNewsSection.model_validate(section)
            for section in data.get("sections") or []
        ],
        generated_at=data.get("generated_at"),
        provider_name=data.get("provider_name"),
        model_name=data.get("model_name"),
        entry_count=int(data.get("entry_count") or 0),
        freshness_hours=int(data.get("freshness_hours") or DEFAULT_FRESHNESS_HOURS),
        error_message=data.get("error_message"),
    )


def _chat_endpoint(base_url: str | None) -> str:
    normalized = (base_url or "").strip().rstrip("/")
    if not normalized:
        raise HTTPException(status_code=400, detail="日报生成需要配置模型 Base URL。")
    if normalized.endswith("/chat/completions"):
        return normalized
    return urljoin(f"{normalized}/", "chat/completions")


def _extract_chat_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [str(part.get("text") or "").strip() for part in content if isinstance(part, dict)]
        return "\n".join(part for part in parts if part).strip()
    return ""


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None:
        return None
    return str(value)
