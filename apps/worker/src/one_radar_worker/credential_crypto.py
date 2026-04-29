from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

SECRET_PREFIX = "enc:v1:"


def _fernet() -> Fernet:
    raw_key = os.getenv("ONERADAR_API_SECRET_KEY", "change-me").encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(raw_key).digest())
    return Fernet(key)


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
