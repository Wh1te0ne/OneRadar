from __future__ import annotations

from dataclasses import dataclass
import base64
import json
from pathlib import Path
import uuid
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


class TranscriptionError(RuntimeError):
    pass


class TranscriptionAdapter(Protocol):
    def transcribe(
        self,
        *,
        audio_path: str,
        mime_type: str | None,
        provider_config: dict[str, Any],
        language: str | None,
    ):
        ...


@dataclass(slots=True)
class OpenAICompatibleTranscriptionAdapter:
    timeout_seconds: int = 900

    def transcribe(
        self,
        *,
        audio_path: str,
        mime_type: str | None,
        provider_config: dict[str, Any],
        language: str | None,
    ):
        from .pipelines.bilibili import BilibiliTranscriptPayload

        api_key = str(provider_config.get("api_key") or "").strip()
        model_name = str(provider_config.get("model_name") or "").strip()
        if not api_key:
            raise TranscriptionError("transcription provider API key is not configured")
        if not model_name:
            raise TranscriptionError("transcription model is not configured")

        endpoint = _transcription_endpoint(str(provider_config.get("base_url") or ""))
        payload = _multipart_payload(
            audio_path=audio_path,
            mime_type=mime_type or "application/octet-stream",
            model_name=model_name,
            language=language,
        )
        request = Request(
            endpoint,
            data=payload.body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": f"multipart/form-data; boundary={payload.boundary}",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except (HTTPError, URLError, TimeoutError) as exc:
            raise TranscriptionError(str(exc)) from exc

        try:
            response_payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TranscriptionError("transcription provider returned invalid JSON") from exc

        full_text, segments = _normalize_transcription_response(response_payload)
        if not full_text and not segments:
            raise TranscriptionError("transcription provider returned an empty transcript")
        if not full_text:
            full_text = "\n".join(str(segment.get("text") or "").strip() for segment in segments if segment.get("text"))

        return BilibiliTranscriptPayload(
            transcript_type="asr",
            language=language or response_payload.get("language"),
            full_text=full_text,
            segments=segments
            or [
                {
                    "start_ms": 0,
                    "end_ms": 0,
                    "text": full_text,
                    "speaker": None,
                }
            ],
            provider_name=str(provider_config.get("provider_name") or ""),
            model_name=model_name,
            confidence_score=None,
        )


@dataclass(slots=True)
class MultipartPayload:
    boundary: str
    body: bytes


def _transcription_endpoint(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    if not normalized:
        raise TranscriptionError("transcription provider base URL is not configured")
    if normalized.endswith("/audio/transcriptions"):
        return normalized
    return urljoin(f"{normalized}/", "audio/transcriptions")


def _multipart_payload(
    *,
    audio_path: str,
    mime_type: str,
    model_name: str,
    language: str | None,
) -> MultipartPayload:
    boundary = f"----OneRadar{uuid.uuid4().hex}"
    file_path = Path(audio_path)
    fields = [("model", model_name), ("response_format", "verbose_json")]
    if language:
        fields.append(("language", language))

    chunks: list[bytes] = []
    for name, value in fields:
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("ascii"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("ascii"),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    chunks.extend(
        [
            f"--{boundary}\r\n".encode("ascii"),
            (
                f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
                f"Content-Type: {mime_type}\r\n\r\n"
            ).encode("utf-8"),
            file_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode("ascii"),
        ]
    )
    return MultipartPayload(boundary=boundary, body=b"".join(chunks))


def _normalize_transcription_response(payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    full_text = str(payload.get("text") or "").strip()
    segments: list[dict[str, Any]] = []
    for entry in payload.get("segments") or []:
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("text") or "").strip()
        if not text:
            continue
        start = entry.get("start", 0)
        end = entry.get("end", start)
        try:
            start_ms = int(round(float(start) * 1000))
            end_ms = int(round(float(end) * 1000))
        except (TypeError, ValueError):
            start_ms = 0
            end_ms = 0
        segments.append(
            {
                "start_ms": max(0, start_ms),
                "end_ms": max(max(0, start_ms), end_ms),
                "text": text,
                "speaker": None,
            }
        )
    return full_text, segments


@dataclass(slots=True)
class DoubaoBigModelTranscriptionAdapter:
    timeout_seconds: int = 900

    def transcribe(
        self,
        *,
        audio_path: str,
        mime_type: str | None,
        provider_config: dict[str, Any],
        language: str | None,
    ):
        from .pipelines.bilibili import BilibiliTranscriptPayload

        doubao_config = dict(provider_config.get("doubao_transcription") or {})
        app_id = str(doubao_config.get("app_id") or "").strip()
        access_token = str(doubao_config.get("access_token") or "").strip()
        if not app_id:
            raise TranscriptionError("Doubao transcription APP ID is not configured")
        if not access_token:
            raise TranscriptionError("Doubao transcription Access Token is not configured")

        resource_id = str(provider_config.get("model_name") or "").strip()
        if not resource_id or not resource_id.startswith("volc."):
            resource_id = "volc.bigasr.auc_turbo"

        audio_data = base64.b64encode(Path(audio_path).read_bytes()).decode("ascii")
        payload = {
            "user": {"uid": app_id},
            "audio": {"data": audio_data},
            "request": {
                "model_name": "bigmodel",
                "enable_punc": True,
                "enable_itn": True,
                "show_utterances": True,
            },
        }
        request = Request(
            "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Api-App-Key": app_id,
                "X-Api-Access-Key": access_token,
                "X-Api-Resource-Id": resource_id,
                "X-Api-Request-Id": str(uuid.uuid4()),
                "X-Api-Sequence": "-1",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                status_code = response.headers.get("X-Api-Status-Code")
                status_message = response.headers.get("X-Api-Message")
                raw = response.read().decode("utf-8", errors="replace")
        except (HTTPError, URLError, TimeoutError) as exc:
            raise TranscriptionError(str(exc)) from exc

        try:
            response_payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TranscriptionError("Doubao transcription returned invalid JSON") from exc

        if status_code and status_code != "20000000":
            raise TranscriptionError(status_message or f"Doubao transcription failed: {status_code}")

        full_text, segments = _normalize_doubao_bigmodel_response(response_payload)
        if not full_text and not segments:
            raise TranscriptionError("Doubao transcription returned an empty transcript")
        if not full_text:
            full_text = "\n".join(str(segment.get("text") or "").strip() for segment in segments if segment.get("text"))

        return BilibiliTranscriptPayload(
            transcript_type="asr",
            language=language or response_payload.get("language"),
            full_text=full_text,
            segments=segments
            or [
                {
                    "start_ms": 0,
                    "end_ms": 0,
                    "text": full_text,
                    "speaker": None,
                }
            ],
            provider_name=str(provider_config.get("provider_name") or "Doubao"),
            model_name=resource_id,
            confidence_score=None,
        )


def select_transcription_adapter(provider_config: dict[str, Any]) -> TranscriptionAdapter:
    if str(provider_config.get("provider_type") or "").strip().lower() == "doubao":
        return DoubaoBigModelTranscriptionAdapter()
    return OpenAICompatibleTranscriptionAdapter()


def is_transcription_configured(provider_config: dict[str, Any]) -> bool:
    if str(provider_config.get("provider_type") or "").strip().lower() == "doubao":
        doubao_config = dict(provider_config.get("doubao_transcription") or {})
        return bool(doubao_config.get("app_id") and doubao_config.get("access_token"))
    return bool(provider_config.get("api_key") and provider_config.get("model_name"))


def _normalize_doubao_bigmodel_response(payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    result = payload.get("result")
    if isinstance(result, list):
        result = result[0] if result else {}
    if not isinstance(result, dict):
        result = {}
    full_text = str(result.get("text") or payload.get("text") or "").strip()
    utterances = result.get("utterances") or payload.get("utterances") or []
    segments: list[dict[str, Any]] = []
    if isinstance(utterances, list):
        for entry in utterances:
            if not isinstance(entry, dict):
                continue
            text = str(entry.get("text") or "").strip()
            if not text:
                continue
            try:
                start_ms = int(entry.get("start_time") or entry.get("start") or 0)
                end_ms = int(entry.get("end_time") or entry.get("end") or start_ms)
            except (TypeError, ValueError):
                start_ms = 0
                end_ms = 0
            segments.append(
                {
                    "start_ms": max(0, start_ms),
                    "end_ms": max(max(0, start_ms), end_ms),
                    "text": text,
                    "speaker": entry.get("speaker"),
                }
            )
    return full_text, segments
