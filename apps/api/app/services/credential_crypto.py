from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

SECRET_PREFIX = "enc:v1:"


def _fernet() -> Fernet:
    raw_key = get_settings().api_secret_key.encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(raw_key).digest())
    return Fernet(key)


def protect_secret(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    token = _fernet().encrypt(normalized.encode("utf-8")).decode("ascii")
    return f"{SECRET_PREFIX}{token}"


def reveal_secret(value: str | None) -> str | None:
    if not value:
        return None
    if not value.startswith(SECRET_PREFIX):
        return value
    token = value[len(SECRET_PREFIX) :].encode("ascii")
    try:
        return _fernet().decrypt(token).decode("utf-8")
    except InvalidToken:
        return None
