from datetime import datetime, timezone

from app.generator import Tick
from app.messaging.enricher import TickEnricher


def _tick(symbol: str, price: float, second: int) -> Tick:
    return Tick(
        symbol=symbol,
        price=price,
        occurred_at=datetime(2026, 1, 1, 0, 0, second, tzinfo=timezone.utc),
    )


def test_first_tick_for_a_symbol_has_no_percent_change():
    enricher = TickEnricher()
    enriched = enricher.enrich(_tick("AAPL", 100.0, 0))

    assert enriched.percent_change is None
    assert enriched.moving_average == 100.0


def test_percent_change_computed_against_previous_price():
    enricher = TickEnricher()
    enricher.enrich(_tick("AAPL", 100.0, 0))
    enriched = enricher.enrich(_tick("AAPL", 110.0, 1))

    assert enriched.percent_change == 10.0


def test_moving_average_rolls_over_window_size():
    enricher = TickEnricher(window_size=3)
    enriched = None
    for i, price in enumerate([10.0, 20.0, 30.0, 40.0]):
        enriched = enricher.enrich(_tick("AAPL", price, i))

    assert enriched.moving_average == 30.0  # window holds only 20, 30, 40


def test_symbols_are_tracked_independently():
    enricher = TickEnricher()
    enricher.enrich(_tick("AAPL", 100.0, 0))
    enriched = enricher.enrich(_tick("GOOG", 200.0, 0))

    assert enriched.percent_change is None
    assert enriched.moving_average == 200.0
