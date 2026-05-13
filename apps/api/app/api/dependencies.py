from __future__ import annotations

from typing import Annotated, AsyncIterator

from fastapi import Header, HTTPException

from app.db.models import User
from app.db.session import SessionLocal
from app.services.integration_tokens import verify_integration_token
from app.services.tokens import verify_auth_token
from app.services.user_context import reset_current_user_id, set_current_user_id


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return authorization[7:].strip()


def _user_exists(user_id) -> bool:
    with SessionLocal() as session:
        return session.get(User, user_id) is not None


async def require_current_user(authorization: Annotated[str | None, Header()] = None) -> AsyncIterator[None]:
    bearer = _bearer_token(authorization)
    if bearer is None:
        raise HTTPException(status_code=401, detail="请先登录")

    user_id = verify_auth_token(bearer)
    if user_id is None:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")

    if not _user_exists(user_id):
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")

    token = set_current_user_id(user_id)
    try:
        yield
    finally:
        reset_current_user_id(token)


async def require_mcp_user(authorization: Annotated[str | None, Header()] = None) -> AsyncIterator[None]:
    bearer = _bearer_token(authorization)
    if bearer is None:
        raise HTTPException(status_code=401, detail="请提供 MCP 集成令牌")

    user_id = verify_auth_token(bearer)
    if user_id is None:
        user_id = verify_integration_token(bearer, required_scope="mcp:read")
    if user_id is None or not _user_exists(user_id):
        raise HTTPException(status_code=401, detail="MCP 集成令牌无效或已失效")

    token = set_current_user_id(user_id)
    try:
        yield
    finally:
        reset_current_user_id(token)
