from datetime import datetime, timezone

from app.generator import Tick
from app.messaging.aggregator import CandleAggregator


def _tick(symbol: str, price: float, second: int) -> Tick:
    return Tick(
        symbol=symbol,
        price=price,
        occurred_at=datetime(2026, 1, 1, 0, 0, second, tzinfo=timezone.utc),
    )


def test_no_candle_emitted_while_ticks_stay_within_the_same_window():
    aggregator = CandleAggregator(window_seconds=5)

    assert aggregator.add_tick(_tick("AAPL", 100.0, 0)) is None
    assert aggregator.add_tick(_tick("AAPL", 105.0, 2)) is None
    assert aggregator.add_tick(_tick("AAPL", 95.0, 4)) is None


def test_candle_closes_with_correct_ohlc_when_window_rolls_over():
    aggregator = CandleAggregator(window_seconds=5)
    aggregator.add_tick(_tick("AAPL", 100.0, 0))
    aggregator.add_tick(_tick("AAPL", 110.0, 1))
    aggregator.add_tick(_tick("AAPL", 90.0, 3))
    candle = aggregator.add_tick(_tick("AAPL", 105.0, 6))

    assert candle is not None
    assert candle.symbol == "AAPL"
    assert candle.open == 100.0
    assert candle.high == 110.0
    assert candle.low == 90.0
    assert candle.close == 90.0


def test_new_window_carries_the_closing_tick_as_its_open():
    aggregator = CandleAggregator(window_seconds=5)
    aggregator.add_tick(_tick("AAPL", 100.0, 0))
    aggregator.add_tick(_tick("AAPL", 105.0, 6))
    second_candle = aggregator.add_tick(_tick("AAPL", 108.0, 11))

    assert second_candle is not None
    assert second_candle.open == 105.0
    assert second_candle.close == 105.0


def test_symbols_are_aggregated_independently():
    aggregator = CandleAggregator(window_seconds=5)
    aggregator.add_tick(_tick("AAPL", 100.0, 0))
    result = aggregator.add_tick(_tick("GOOG", 200.0, 0))

    assert result is None
