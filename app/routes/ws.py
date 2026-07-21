from __future__ import annotations

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from app.config import settings
from app.messaging.connection_manager import manager

router = APIRouter()


def _normalize(values: list[str] | None) -> set[str]:
    if not values:
        return set()
    return {value.strip().upper() for value in values if isinstance(value, str) and value.strip()}


def _parse_query_symbols(raw: str | None) -> set[str]:
    return _normalize(raw.split(",")) if raw else set()


async def _send_subscriptions(websocket: WebSocket) -> None:
    await websocket.send_json(
        {"type": "subscriptions", "symbols": sorted(manager.subscriptions_for(websocket))}
    )


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, symbols: str | None = Query(default=None)):
    origin = websocket.headers.get("origin")
    if origin is not None and origin not in settings.allowed_origins_list:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    manager.connect(websocket, _parse_query_symbols(symbols))
    await _send_subscriptions(websocket)

    try:
        while True:
            message = await websocket.receive_json()
            action = message.get("action")
            requested = _normalize(message.get("symbols"))

            if action == "subscribe":
                manager.subscribe(websocket, requested)
            elif action == "unsubscribe":
                manager.unsubscribe(websocket, requested)
            else:
                continue

            await _send_subscriptions(websocket)
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)
