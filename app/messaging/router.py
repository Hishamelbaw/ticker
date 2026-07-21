from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any


class EventType(str, Enum):
    TICK = "tick"
    ALERT_CHECK = "alert_check"
    CANDLE_CLOSE = "candle_close"


@dataclass(frozen=True)
class Event:
    type: EventType
    payload: Any


Handler = Callable[[Event], Awaitable[None]]


class MessageRouter:
    """Single dispatch point for internal events, keyed by event type.

    Replaces scattered `if event.type == ...` checks with one place where
    handlers register interest in a given event type.
    """

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[Handler]] = {}

    def register(self, event_type: EventType, handler: Handler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    async def dispatch(self, event: Event) -> None:
        for handler in self._handlers.get(event.type, []):
            await handler(event)
