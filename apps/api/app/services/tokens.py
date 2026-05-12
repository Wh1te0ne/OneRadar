from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import Any

from app.core.config import get_settings


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(raw: str) -> bytes:
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))


def _sign(payload: str) -> str:
    settings = get_settings()
    digest = hmac.new(
        settings.api_secret_key.encode("utf-8"),
        payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return _b64encode(digest)


def create_auth_token(user_id: uuid.UUID) -> str:
    settings = get_settings()
    now = int(time.time())
    body = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + settings.auth_token_ttl_seconds,
    }
    payload = _b64encode(json.dumps(body, separators=(",", ":")).encode("utf-8"))
    return f"{payload}.{_sign(payload)}"


def verify_auth_token(token: str) -> uuid.UUID | None:
    try:
        payload, signature = token.split(".", 1)
    except ValueError:
        return None
    if not hmac.compare_digest(_sign(payload), signature):
        return None
    try:
        body: dict[str, Any] = json.loads(_b64decode(payload))
        if int(body.get("exp", 0)) < int(time.time()):
            return None
        return uuid.UUID(str(body["sub"]))
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
