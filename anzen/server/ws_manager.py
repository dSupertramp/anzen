"""
WebSocket connection manager.
Broadcasts new events to all connected dashboard clients in real-time.
"""

import asyncio
import json
import logging
from typing import Set
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self._connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)
        logger.info(f"Dashboard connected. Total: {len(self._connections)}")

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            self._connections.discard(ws)
        logger.info(f"Dashboard disconnected. Total: {len(self._connections)}")

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected dashboard clients."""
        if not self._connections:
            return
        payload = json.dumps(message)
        dead = set()
        async with self._lock:
            connections = set(self._connections)
        for ws in connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        if dead:
            async with self._lock:
                self._connections -= dead

    @property
    def active_connections(self) -> int:
        return len(self._connections)


# Singleton
manager = ConnectionManager()
