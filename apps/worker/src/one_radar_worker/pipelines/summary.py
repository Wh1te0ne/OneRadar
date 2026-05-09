from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from .common import PipelineContext, PipelineRunResult, PipelineStepResult


@dataclass(slots=True)
class SummaryResult:
    ok: bool
    content: str
    provider_name: str | None = None
    model_name: str | None = None
    error_message: str | None = None


SOURCE_TEXT_LIMIT = 80000
SOURCE_DESCRIPTION_LIMIT = 6000


class OpenAICompatibleSummaryAdapter:
    def __init__(self, timeout_seconds: int = 120):
        self.timeout_seconds = timeout_seconds

    def summarize(
        self,
        *,
        provider_config: dict[str, Any],
        title: str,
        source_text: str,
    ) -> SummaryResult:
        api_key = str(provider_config.get("api_key") or "").strip()
        model_name = str(provider_config.get("model_name") or "").strip()
        if not api_key:
            return SummaryResult(ok=False, content="", error_message="summary provider API key is not configured")
        if not model_name:
            return SummaryResult(ok=False, content="", error_message="summary provider model is not configured")

        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "user",
                    "content": _summary_prompt(
                        title=title,
                        source_text=source_text,
                        content_type=str(provider_config.get("content_type") or ""),
                    ),
                }
            ],
            "temperature": 0.2,
            "max_tokens": 5200,
        }
        _apply_thinking_payload(payload, provider_config=provider_config)
        request = Request(
            _chat_endpoint(str(provider_config.get("base_url") or "")),
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8", errors="replace"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            return SummaryResult(ok=False, content="", error_message=str(exc))

        content = _extract_chat_text(response_payload)
        if not content:
            return SummaryResult(ok=False, content="", error_message="summary provider returned an empty response")
        return SummaryResult(
            ok=True,
            content=content,
            provider_name=str(provider_config.get("provider_name") or ""),
            model_name=model_name,
        )


class SummaryPipeline:
    def __init__(self, adapter: OpenAICompatibleSummaryAdapter | None = None):
        self.adapter = adapter or OpenAICompatibleSummaryAdapter()

    def run(self, context: PipelineContext) -> PipelineRunResult:
        provider_config = dict(context.payload.get("summary_provider") or {})
        provider_config["content_type"] = str(context.payload.get("content_type") or "")
        source_text = _source_text(context.payload)
        title = str(context.payload.get("title") or "未命名内容")

        if not provider_config:
            return _failure("summary provider is not configured")
        if not source_text.strip():
            return _failure("summary source text is empty")

        result = self.adapter.summarize(
            provider_config=provider_config,
            title=title,
            source_text=source_text,
        )
        if not result.ok:
            return _failure(result.error_message or "summary generation failed")

        return PipelineRunResult(
            ok=True,
            steps=[
                PipelineStepResult(
                    step_name="generate_summary",
                    ok=True,
                    message="summary generated",
                )
            ],
            data={
                "source_url": context.source_url,
                "fetch": {
                    "mode": "summary",
                    "final_url": context.source_url,
                },
                "persistable": {
                    "content_item": {
                        "title": title,
                        "raw_meta": {
                            "summary_generated_at": "worker",
                        },
                    },
                    "summaries": [
                        {
                            "summary_type": "short",
                            "content": result.content,
                            "provider_name": result.provider_name,
                            "model_name": result.model_name,
                            "version": 1,
                        }
                    ],
                },
            },
        )


def _failure(message: str) -> PipelineRunResult:
    return PipelineRunResult(
        ok=False,
        steps=[PipelineStepResult(step_name="generate_summary", ok=False, message=message)],
        data={"persistable": {}},
    )


def _source_text(payload: dict[str, Any]) -> str:
    content_type = str(payload.get("content_type") or "").strip()

    if content_type in {"podcast_episode", "bilibili_video"}:
        transcript_text = _transcript_text(payload)
        description_text = _parsed_document_text(payload) or str(payload.get("summary") or payload.get("description") or "").strip()
        sections: list[str] = []
        if description_text:
            sections.append(f"节目/来源简介：\n{description_text[:SOURCE_DESCRIPTION_LIMIT]}")
        if transcript_text:
            sections.append(f"转写全文：\n{transcript_text[:SOURCE_TEXT_LIMIT]}")
        if sections:
            return "\n\n".join(sections)[:SOURCE_TEXT_LIMIT]

    parsed_text = _parsed_document_text(payload)
    if parsed_text:
        return parsed_text[:SOURCE_TEXT_LIMIT]

    transcript_text = _transcript_text(payload)
    if transcript_text:
        return transcript_text[:SOURCE_TEXT_LIMIT]

    summary = str(payload.get("summary") or "").strip()
    if summary:
        return summary[:SOURCE_TEXT_LIMIT]
    return str(payload.get("description") or "").strip()[:SOURCE_TEXT_LIMIT]


def _parsed_document_text(payload: dict[str, Any]) -> str:
    parsed_document = payload.get("parsed_document")
    if isinstance(parsed_document, dict):
        text = str(parsed_document.get("plain_text") or "").strip()
        if text:
            return text
    return ""


def _transcript_text(payload: dict[str, Any]) -> str:
    transcript = payload.get("transcript")
    if isinstance(transcript, dict):
        text = str(transcript.get("full_text") or "").strip()
        if text:
            return text
        segments = transcript.get("segments")
        if isinstance(segments, list):
            joined = "\n".join(
                _segment_text(segment)
                for segment in segments
                if isinstance(segment, dict) and _segment_text(segment)
            )
            if joined:
                return joined
    return ""


def _segment_text(segment: dict[str, Any]) -> str:
    text = str(segment.get("text") or "").strip()
    if not text:
        return ""
    start_ms = segment.get("start_ms")
    if isinstance(start_ms, (int, float)):
        total_seconds = max(0, int(start_ms / 1000))
        return f"[{total_seconds // 60:02d}:{total_seconds % 60:02d}] {text}"
    return text


def _summary_prompt(*, title: str, source_text: str, content_type: str = "") -> str:
    if content_type in {"podcast_episode", "bilibili_video"}:
        instruction = (
            "这是一段长音视频内容。请先判断它更接近哪一种类型：叙事闲聊/旅行故事/访谈，还是行业分析/知识讲解/观点讨论。请输出中文深度摘要，要求：\n"
            "1. 不要编造内容，不要把节目简介当作完整内容本身；优先依据转写全文。\n"
            "2. 使用 Markdown 格式组织内容。分区标题使用二级标题，例如 ## 总览；要点使用项目符号，格式为：- **短标签**：具体内容。\n"
            "3. 如果是普通闲聊、旅行见闻、生活故事或综艺型播客，使用这些分区：## 总览、## 顺着节目听下来、## 有用提醒。其中 ## 顺着节目听下来 用 4-7 个自然段按时间顺序讲清故事，不要给每段硬加小标题，不要强行抽象成观点；## 有用提醒 只有确实有旅行、消费、安全等可复用信息时才用项目符号。\n"
            "4. 如果是行业分析、知识讲解或观点讨论，使用这些分区：## 总览、## 核心结论、## 关键事实与证据、## 行动或追踪问题。除叙事段落外，分区下用项目符号。\n"
            "5. 对叙事类内容，允许较长但要顺畅；对行业/知识类内容，要拆清结论、证据、数字、因果和待追踪问题。\n"
            "6. 如果转写中有时间戳，可在相关位置简短标注。不输出逐字稿，不输出寒暄，不使用表格。\n"
        )
    else:
        instruction = (
            "请输出中文阅读摘要，要求：\n"
            "1. 不要编造原文没有的信息。\n"
            "2. 使用 Markdown 格式组织内容。分区标题使用二级标题，例如 ## 总览；要点使用项目符号，格式为：- **短标签**：具体内容。\n"
            "3. 输出 ## 总览、## 核心要点、## 重要细节、## 后续关注 四个分区。\n"
            "4. ## 总览 用 1-2 个自然段讲清主题、背景、核心结论和为什么重要。\n"
            "5. ## 核心要点 保留主要观点、关键事实、数字、对比、因果关系和限制条件，不要只写抽象结论。\n"
            "6. ## 重要细节 承接核心要点，整理原文中值得单独记住的名称、数据、链接线索、案例、适用场景、限制条件、争议或风险；不要重复总览，也不要把内容硬凑成行动清单。\n"
            "7. ## 后续关注 只写真正需要继续跟进、验证或回看原文的事项，例如待观察影响、未解决问题、可尝试的工具/接口/方法、进一步阅读线索；如果原文没有这类内容，写“原文没有明确的后续关注事项”。\n"
            "8. 摘要可以比普通短摘要更充分，优先完整保留有复用价值的信息；不要为了简短而省略原文中的参数、示例、限制、数字和关键引用线索。\n"
            "9. 不输出寒暄，不使用表格。\n"
        )
    return (
        "你是 OneRadar 的知识整理助手。"
        f"{instruction}\n"
        f"标题：{title}\n\n"
        f"内容：\n{source_text}"
    )


def _chat_endpoint(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    if not normalized:
        raise ValueError("summary provider base URL is not configured")
    if normalized.endswith("/chat/completions"):
        return normalized
    return urljoin(f"{normalized}/", "chat/completions")


def _thinking_mode(provider_config: dict[str, Any]) -> str:
    runtime_config = provider_config.get("provider_config")
    if not isinstance(runtime_config, dict):
        runtime_config = {}
    llm_config = runtime_config.get("llm")
    if not isinstance(llm_config, dict):
        llm_config = {}
    mode = str(llm_config.get("thinking_mode") or "default").strip().lower()
    if mode == "auto":
        return "enabled"
    if mode in {"default", "enabled", "disabled"}:
        return mode
    return "default"


def _apply_thinking_payload(payload: dict[str, Any], *, provider_config: dict[str, Any]) -> None:
    mode = _thinking_mode(provider_config)
    if mode == "default":
        return
    provider_type = str(provider_config.get("provider_type") or "").strip().lower()
    if provider_type == "deepseek":
        payload["thinking"] = {"type": mode}
        if mode == "enabled":
            payload["reasoning_effort"] = "medium"
        payload.pop("temperature", None)
        return
    if provider_type == "doubao":
        payload["thinking"] = {"type": mode}
        payload.pop("temperature", None)


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
