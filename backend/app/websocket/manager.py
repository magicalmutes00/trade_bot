"""WebSocket connection hub — fan-out with dead-client pruning."""

import asyncio
import json
from typing import Any

from fastapi import WebSocket

from app.core.logging import get_logger

logger = get_logger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    @property
    def count(self) -> int:
        return len(self._clients)

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._clients.add(websocket)
        logger.info("ws client connected (total=%d)", self.count)

    def disconnect(self, websocket: WebSocket) -> None:
        self._clients.discard(websocket)

    async def send_personal(self, websocket: WebSocket, payload: dict[str, Any]) -> None:
        await websocket.send_text(json.dumps(payload, default=str))

    async def broadcast(self, payload: dict[str, Any]) -> int:
        """Send to every client; silently drop connections that fail."""
        if not self._clients:
            return 0
        message = json.dumps(payload, default=str)
        results = await asyncio.gather(
            *(c.send_text(message) for c in list(self._clients)),
            return_exceptions=True,
        )
        dead = [
            client for client, res in zip(list(self._clients), results)
            if isinstance(res, BaseException)
        ]
        for client in dead:
            self.disconnect(client)
        if dead:
            logger.info("ws pruned %d dead client(s)", len(dead))
        return len(self._clients) - len(dead)


manager = ConnectionManager()

__all__ = ["ConnectionManager", "manager"]
