from datetime import datetime, timedelta, timezone

from app.alerts.state_machine import ACKNOWLEDGED, ARMED, CANCELLED, EXPIRED, TRIGGERED, state_for
from app.models import Alert


def _alert(**overrides) -> Alert:
    defaults = dict(
        symbol="AAPL",
        threshold=150.0,
        direction="above",
        expires_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ack_window_seconds=60,
        current_state="armed",
        triggered_at=None,
    )
    defaults.update(overrides)
    return Alert(**defaults)


def test_armed_triggers_when_price_crosses_above_threshold():
    alert = _alert(direction="above", threshold=150.0)
    assert ARMED.on_tick(alert, 150.5) is TRIGGERED


def test_armed_stays_armed_when_price_has_not_crossed():
    alert = _alert(direction="above", threshold=150.0)
    assert ARMED.on_tick(alert, 149.0) is ARMED


def test_armed_triggers_when_price_crosses_below_threshold():
    alert = _alert(direction="below", threshold=100.0)
    assert ARMED.on_tick(alert, 99.5) is TRIGGERED


def test_armed_cancel_transitions_to_cancelled():
    alert = _alert()
    assert ARMED.on_cancel(alert) is CANCELLED


def test_armed_time_check_expires_past_expiry():
    alert = _alert(expires_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    assert ARMED.on_time_check(alert, now) is EXPIRED


def test_armed_time_check_stays_armed_before_expiry():
    alert = _alert(expires_at=datetime(2026, 1, 2, tzinfo=timezone.utc))
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert ARMED.on_time_check(alert, now) is ARMED


def test_armed_ack_is_illegal_and_is_a_no_op():
    alert = _alert()
    assert ARMED.on_ack(alert) is ARMED


def test_triggered_ack_transitions_to_acknowledged():
    alert = _alert(current_state="triggered")
    assert TRIGGERED.on_ack(alert) is ACKNOWLEDGED


def test_triggered_time_check_expires_after_ack_window():
    triggered_at = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    alert = _alert(current_state="triggered", triggered_at=triggered_at, ack_window_seconds=60)
    now = triggered_at + timedelta(seconds=61)
    assert TRIGGERED.on_time_check(alert, now) is EXPIRED


def test_triggered_time_check_stays_triggered_within_ack_window():
    triggered_at = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    alert = _alert(current_state="triggered", triggered_at=triggered_at, ack_window_seconds=60)
    now = triggered_at + timedelta(seconds=30)
    assert TRIGGERED.on_time_check(alert, now) is TRIGGERED


def test_triggered_cancel_is_illegal_and_is_a_no_op():
    alert = _alert(current_state="triggered")
    assert TRIGGERED.on_cancel(alert) is TRIGGERED


def test_triggered_tick_does_not_retrigger():
    alert = _alert(current_state="triggered", direction="above", threshold=150.0)
    assert TRIGGERED.on_tick(alert, 999.0) is TRIGGERED


def test_acknowledged_state_is_terminal_for_every_event():
    alert = _alert(current_state="acknowledged")
    assert ACKNOWLEDGED.on_tick(alert, 999.0) is ACKNOWLEDGED
    assert ACKNOWLEDGED.on_ack(alert) is ACKNOWLEDGED
    assert ACKNOWLEDGED.on_cancel(alert) is ACKNOWLEDGED
    assert ACKNOWLEDGED.on_time_check(alert, datetime.now(timezone.utc)) is ACKNOWLEDGED


def test_state_for_looks_up_state_by_current_state_string():
    assert state_for("armed") is ARMED
    assert state_for("triggered") is TRIGGERED
    assert state_for("acknowledged") is ACKNOWLEDGED
    assert state_for("expired") is EXPIRED
    assert state_for("cancelled") is CANCELLED
