import asyncio
import logging
import random
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger("ticker.generator")

SYMBOLS = ["AAPL", "GOOG", "MSFT", "TSLA", "AMZN"]
STARTING_PRICES = {
    "AAPL": 195.00,
    "GOOG": 175.00,
    "MSFT": 420.00,
    "TSLA": 250.00,
    "AMZN": 185.00,
}
TICK_INTERVAL_SECONDS = 1.0
MAX_STEP_PCT = 0.003


@dataclass(frozen=True)
class Tick:
    symbol: str
    price: float
    occurred_at: datetime


class TickGenerator:
    def __init__(
        self,
        symbols: list[str] = SYMBOLS,
        starting_prices: dict[str, float] = STARTING_PRICES,
        interval_seconds: float = TICK_INTERVAL_SECONDS,
    ) -> None:
        self._symbols = symbols
        self._prices = dict(starting_prices)
        self._interval_seconds = interval_seconds

    def _next_price(self, symbol: str) -> float:
        # Bounded random walk keeps prices plausible without a real market-data feed.
        current = self._prices[symbol]
        pct_move = random.uniform(-MAX_STEP_PCT, MAX_STEP_PCT)
        updated = max(0.01, current * (1 + pct_move))
        self._prices[symbol] = updated
        return round(updated, 2)

    async def stream(self) -> AsyncIterator[Tick]:
        while True:
            for symbol in self._symbols:
                yield Tick(
                    symbol=symbol,
                    price=self._next_price(symbol),
                    occurred_at=datetime.now(timezone.utc),
                )
            await asyncio.sleep(self._interval_seconds)


async def run_generator(generator: TickGenerator) -> None:
    # Placeholder sink until messaging/router.py exists (step 3) to dispatch these.
    async for tick in generator.stream():
        logger.info("tick %s $%.2f @ %s", tick.symbol, tick.price, tick.occurred_at.isoformat())
