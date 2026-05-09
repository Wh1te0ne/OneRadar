from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.services.mcp_news_service import handle_mcp_request

router = APIRouter(prefix="/mcp", tags=["mcp"])


@router.post("")
def mcp_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("jsonrpc") != "2.0":
        raise HTTPException(status_code=400, detail="MCP requests must use JSON-RPC 2.0.")
    return handle_mcp_request(payload)
