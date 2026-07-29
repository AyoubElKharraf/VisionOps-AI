"""Shared API-key authentication for REST and WebSocket."""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, Query, WebSocket, WebSocketException, status

from app.config import get_settings

API_KEY_HEADER = "X-API-Key"


def _keys_match(provided: str | None, expected: str) -> bool:
    if not provided:
        return False
    return secrets.compare_digest(provided, expected)


def require_api_key(
    x_api_key: str | None = Header(default=None, alias=API_KEY_HEADER),
    api_key: str | None = Query(default=None),
) -> None:
    """
    Protect /api/v1 routes when VISIONOPS_API_KEY is configured.
    Accepts X-API-Key header or ?api_key= (useful for simple clients).
    """
    expected = get_settings().visionops_api_key
    if not expected:
        return
    if not _keys_match(x_api_key or api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )


async def accept_websocket_api_key(websocket: WebSocket) -> None:
    """
    Validate WebSocket clients. Browsers cannot set custom headers reliably,
    so the key is accepted via ?api_key= or X-API-Key.
    """
    expected = get_settings().visionops_api_key
    if not expected:
        return

    provided = websocket.query_params.get("api_key") or websocket.headers.get("x-api-key")
    if _keys_match(provided, expected):
        return

    raise WebSocketException(code=4401, reason="Invalid or missing API key")
