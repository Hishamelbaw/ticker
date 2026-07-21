from __future__ import annotations

import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger("ticker.connection_manager")


class ConnectionManager:
    """Observer subject for the Publish-Subscribe EIP.

    Each connected WebSocket is an observer with its own subscribed symbol
    set; a broadcast for a symbol only reaches observers subscribed to it.
    """

    def __init__(self) -> None:
        self._subscriptions: dict[WebSocket, set[str]] = {}

    def connect(self, websocket: WebSocket, symbols: set[str]) -> None:
        self._subscriptions[websocket] = set(symbols)

    def disconnect(self, websocket: WebSocket) -> None:
        self._subscriptions.pop(websocket, None)

    def subscribe(self, websocket: WebSocket, symbols: set[str]) -> None:
        self._subscriptions.setdefault(websocket, set()).update(symbols)

    def unsubscribe(self, websocket: WebSocket, symbols: set[str]) -> None:
        if websocket in self._subscriptions:
            self._subscriptions[websocket].difference_update(symbols)

    def subscriptions_for(self, websocket: WebSocket) -> set[str]:
        return set(self._subscriptions.get(websocket, set()))

    def subscriber_count(self, symbol: str) -> int:
        return sum(1 for symbols in self._subscriptions.values() if symbol in symbols)

    async def broadcast(self, symbol: str, message: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for websocket, symbols in self._subscriptions.items():
            if symbol not in symbols:
                continue
            try:
                await websocket.send_json(message)
            except Exception:
                dead.append(websocket)

        for websocket in dead:
            self.disconnect(websocket)


manager = ConnectionManager()
