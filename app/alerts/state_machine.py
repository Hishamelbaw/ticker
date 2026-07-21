from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models import Alert


def _as_aware_utc(value: datetime) -> datetime:
    # SQLite drops tzinfo on round-trip even for DateTime(timezone=True)
    # columns, so a value freshly constructed in-memory (aware) and the same
    # value read back after a commit (naive) must compare equal here.
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _crosses_threshold(alert: Alert, price: float) -> bool:
    # "Crosses" is evaluated as "has reached" rather than tracking the prior
    # tick: once Armed fires it leaves the Armed state, so there is no
    # re-trigger risk from treating each qualifying tick as a crossing.
    if alert.direction == "above":
        return price >= alert.threshold
    return price <= alert.threshold


def _ack_deadline(alert: Alert) -> datetime | None:
    if alert.triggered_at is None:
        return None
    return _as_aware_utc(alert.triggered_at) + timedelta(seconds=alert.ack_window_seconds)


class AlertState:
    """Base State: every handler defaults to a no-op (returns self).

    Concrete states override only the events the state chart in
    ARCHITECTURE.md defines for them, so an event with no matching
    transition is an explicit, deliberate no-op rather than something that
    slips through unhandled.
    """

    name: str

    def on_tick(self, alert: Alert, price: float) -> AlertState:
        return self

    def on_ack(self, alert: Alert) -> AlertState:
        return self

    def on_cancel(self, alert: Alert) -> AlertState:
        return self

    def on_time_check(self, alert: Alert, now: datetime) -> AlertState:
        return self


class ArmedState(AlertState):
    name = "armed"

    def on_tick(self, alert: Alert, price: float) -> AlertState:
        return TRIGGERED if _crosses_threshold(alert, price) else self

    def on_cancel(self, alert: Alert) -> AlertState:
        return CANCELLED

    def on_time_check(self, alert: Alert, now: datetime) -> AlertState:
        return EXPIRED if _as_aware_utc(now) > _as_aware_utc(alert.expires_at) else self


class TriggeredState(AlertState):
    name = "triggered"

    def on_ack(self, alert: Alert) -> AlertState:
        return ACKNOWLEDGED

    def on_time_check(self, alert: Alert, now: datetime) -> AlertState:
        deadline = _ack_deadline(alert)
        if deadline is not None and _as_aware_utc(now) > deadline:
            return EXPIRED
        return self


class AcknowledgedState(AlertState):
    name = "acknowledged"


class ExpiredState(AlertState):
    name = "expired"


class CancelledState(AlertState):
    name = "cancelled"


ARMED = ArmedState()
TRIGGERED = TriggeredState()
ACKNOWLEDGED = AcknowledgedState()
EXPIRED = ExpiredState()
CANCELLED = CancelledState()

_STATES: dict[str, AlertState] = {
    state.name: state for state in (ARMED, TRIGGERED, ACKNOWLEDGED, EXPIRED, CANCELLED)
}


def state_for(name: str) -> AlertState:
    return _STATES[name]
