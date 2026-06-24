from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import IntegrationToken
from app.db.session import SessionLocal
from app.schemas.integration_tokens import (
    IntegrationTokenCreateRequest,
    IntegrationTokenCreateResponse,
    IntegrationTokenEntry,
    IntegrationTokenListResponse,
    IntegrationTokenRevokeResponse,
    IntegrationTokenUpdateRequest,
)
from app.services.db_access import get_primary_user

TOKEN_PREFIX = "ort_"
DEFAULT_SCOPES = {"mcp:read", "analysis:write"}


def _hash_token(token: str) -> str:
    settings = get_settings()
    return hmac.new(
        settings.api_secret_key.encode("utf-8"),
        token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _new_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def _clean_scopes(scopes: list[str]) -> list[str]:
    cleaned = sorted({scope.strip() for scope in scopes if scope.strip()})
    if not cleaned:
        return sorted(DEFAULT_SCOPES)
    unsupported = set(cleaned) - DEFAULT_SCOPES
    if unsupported:
        raise ValueError("不支持的令牌权限范围")
    return cleaned


def _to_entry(token: IntegrationToken) -> IntegrationTokenEntry:
    return IntegrationTokenEntry(
        id=str(token.id),
        name=token.name,
        token_prefix=token.token_prefix,
        scopes=list(token.scopes),
        created_at=token.created_at,
        last_used_at=token.last_used_at,
        revoked_at=token.revoked_at,
    )


def create_integration_token(
    payload: IntegrationTokenCreateRequest,
) -> IntegrationTokenCreateResponse:
    name = payload.name.strip()
    if not name:
        raise ValueError("请输入令牌名称")
    scopes = _clean_scopes(payload.scopes)
    raw_token = _new_token()
    with SessionLocal() as session:
        user = get_primary_user(session)
        token = IntegrationToken(
            user_id=user.id,
            name=name,
            token_hash=_hash_token(raw_token),
            token_prefix=raw_token[:12],
            scopes=scopes,
        )
        session.add(token)
        session.flush()
        entry = _to_entry(token)
        session.commit()
        return IntegrationTokenCreateResponse(item=entry, token=raw_token)


def list_integration_tokens() -> IntegrationTokenListResponse:
    with SessionLocal() as session:
        user = get_primary_user(session)
        tokens = (
            session.execute(
                select(IntegrationToken)
                .where(
                    IntegrationToken.user_id == user.id,
                    IntegrationToken.revoked_at.is_(None),
                )
                .order_by(IntegrationToken.created_at.desc())
            )
            .scalars()
            .all()
        )
        return IntegrationTokenListResponse(items=[_to_entry(token) for token in tokens])


def update_integration_token(
    token_id: str,
    payload: IntegrationTokenUpdateRequest,
) -> IntegrationTokenEntry:
    name = payload.name.strip()
    if not name:
        raise ValueError("请输入令牌名称")
    try:
        parsed_id = uuid.UUID(token_id)
    except ValueError as exc:
        raise ValueError("令牌不存在") from exc
    with SessionLocal() as session:
        user = get_primary_user(session)
        token = session.get(IntegrationToken, parsed_id)
        if token is None or token.user_id != user.id or token.revoked_at is not None:
            raise ValueError("令牌不存在")
        token.name = name
        session.add(token)
        session.flush()
        entry = _to_entry(token)
        session.commit()
        return entry


def revoke_integration_token(token_id: str) -> IntegrationTokenRevokeResponse:
    try:
        parsed_id = uuid.UUID(token_id)
    except ValueError as exc:
        raise ValueError("令牌不存在") from exc
    with SessionLocal() as session:
        user = get_primary_user(session)
        token = session.get(IntegrationToken, parsed_id)
        if token is None or token.user_id != user.id:
            raise ValueError("令牌不存在")
        if token.revoked_at is None:
            token.revoked_at = datetime.now(timezone.utc)
            session.add(token)
            session.flush()
        session.commit()
        return IntegrationTokenRevokeResponse(id=str(token.id), revoked=True)


def verify_integration_token(raw_token: str, required_scope: str) -> uuid.UUID | None:
    token_hash = _hash_token(raw_token)
    with SessionLocal() as session:
        token = (
            session.execute(
                select(IntegrationToken)
                .where(
                    IntegrationToken.token_hash == token_hash,
                    IntegrationToken.revoked_at.is_(None),
                )
                .limit(1)
            )
            .scalars()
            .first()
        )
        if token is None or required_scope not in token.scopes:
            return None
        token.last_used_at = datetime.now(timezone.utc)
        session.add(token)
        session.commit()
        return token.user_id
