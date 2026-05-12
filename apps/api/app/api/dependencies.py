from __future__ import annotations

from typing import Annotated, AsyncIterator

from fastapi import Header, HTTPException

from app.db.models import User
from app.db.session import SessionLocal
from app.services.tokens import verify_auth_token
from app.services.user_context import reset_current_user_id, set_current_user_id


async def require_current_user(authorization: Annotated[str | None, Header()] = None) -> AsyncIterator[None]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="请先登录")

    user_id = verify_auth_token(authorization[7:].strip())
    if user_id is None:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")

    with SessionLocal() as session:
        if session.get(User, user_id) is None:
            raise HTTPException(status_code=401, detail="登录已失效，请重新登录")

    token = set_current_user_id(user_id)
    try:
        yield
    finally:
        reset_current_user_id(token)
