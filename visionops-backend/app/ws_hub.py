"""In-memory hub for live detection WebSocket fan-out."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger("visionops.ws")


class DetectionHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self.latest: dict[str, Any] | None = None

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._clients.add(websocket)
        logger.info("WS client connected (%d total)", len(self._clients))
        if self.latest is not None:
            await websocket.send_json(self.latest)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(websocket)
        logger.info("WS client disconnected (%d total)", len(self._clients))

    async def broadcast(self, payload: dict[str, Any]) -> int:
        self.latest = payload
        async with self._lock:
            clients = list(self._clients)
        dead: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_json(payload)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)
        return len(clients) - len(dead)


detection_hub = DetectionHub()
