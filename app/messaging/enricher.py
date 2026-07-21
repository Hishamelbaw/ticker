from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime

from app.generator import Tick

DEFAULT_WINDOW_SIZE = 5


@dataclass(frozen=True)
class EnrichedTick:
    symbol: str
    price: float
    occurred_at: datetime
    percent_change: float | None
    moving_average: float


class TickEnricher:
    """Adds percent-change and rolling-moving-average fields to a raw tick.

    Keeps a small per-symbol price history so it can compute fields a single
    tick can't express on its own.
    """

    def __init__(self, window_size: int = DEFAULT_WINDOW_SIZE) -> None:
        self._window_size = window_size
        self._history: dict[str, deque[float]] = {}

    def enrich(self, tick: Tick) -> EnrichedTick:
        history = self._history.setdefault(tick.symbol, deque(maxlen=self._window_size))

        previous_price = history[-1] if history else None
        percent_change = (
            round((tick.price - previous_price) / previous_price * 100, 4)
            if previous_price is not None
            else None
        )

        history.append(tick.price)
        moving_average = round(sum(history) / len(history), 4)

        return EnrichedTick(
            symbol=tick.symbol,
            price=tick.price,
            occurred_at=tick.occurred_at,
            percent_change=percent_change,
            moving_average=moving_average,
        )
