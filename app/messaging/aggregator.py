from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.generator import Tick

DEFAULT_WINDOW_SECONDS = 5


@dataclass(frozen=True)
class Candle:
    symbol: str
    open: float
    high: float
    low: float
    close: float
    window_start: datetime
    window_end: datetime


class _CandleBuilder:
    def __init__(self, symbol: str, window_start: datetime, price: float) -> None:
        self.symbol = symbol
        self.window_start = window_start
        self.open = price
        self.high = price
        self.low = price
        self.close = price

    def add(self, price: float) -> None:
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price

    def build(self, window_end: datetime) -> Candle:
        return Candle(
            symbol=self.symbol,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            window_start=self.window_start,
            window_end=window_end,
        )


class CandleAggregator:
    """Combines raw ticks into OHLC candles over a fixed rolling window per symbol.

    Publishes on a logically separate `candles` topic: `add_tick` returns a
    completed Candle whenever a tick lands outside its symbol's current
    window, and None otherwise.
    """

    def __init__(self, window_seconds: int = DEFAULT_WINDOW_SECONDS) -> None:
        self._window_seconds = window_seconds
        self._builders: dict[str, _CandleBuilder] = {}

    def _window_start(self, occurred_at: datetime) -> datetime:
        epoch_seconds = occurred_at.timestamp()
        bucket_seconds = epoch_seconds - (epoch_seconds % self._window_seconds)
        return datetime.fromtimestamp(bucket_seconds, tz=timezone.utc)

    def add_tick(self, tick: Tick) -> Candle | None:
        window_start = self._window_start(tick.occurred_at)
        builder = self._builders.get(tick.symbol)

        if builder is None:
            self._builders[tick.symbol] = _CandleBuilder(tick.symbol, window_start, tick.price)
            return None

        if window_start > builder.window_start:
            completed = builder.build(window_end=window_start)
            self._builders[tick.symbol] = _CandleBuilder(tick.symbol, window_start, tick.price)
            return completed

        builder.add(tick.price)
        return None
