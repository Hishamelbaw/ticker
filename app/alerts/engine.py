from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts.state_machine import state_for
from app.audit.event_log import append_event
from app.generator import Tick
from app.models import Alert


def _commit_transition(
    session: Session, alert: Alert, new_state_name: str, *, event_type: str, payload: dict[str, Any]
) -> None:
    now = datetime.now(timezone.utc)
    if new_state_name == "triggered" and alert.triggered_at is None:
        alert.triggered_at = now
    alert.current_state = new_state_name
    session.add(alert)

    # append_event() commits: the alert's new state and its EventLog row
    # land in the same transaction, so the audit trail and the materialized
    # state can never disagree about whether a transition happened.
    append_event(
        session,
        entity_type="alert",
        entity_id=str(alert.id),
        event_type=event_type,
        payload={**payload, "new_state": new_state_name},
        occurred_at=now,
    )


def apply_price_tick(session: Session, alert: Alert, price: float) -> bool:
    old_state = state_for(alert.current_state)
    new_state = old_state.on_tick(alert, price)
    if new_state is old_state:
        return False
    _commit_transition(session, alert, new_state.name, event_type="PRICE_TICK", payload={"price": price})
    return True


def apply_time_check(session: Session, alert: Alert, now: datetime) -> bool:
    old_state = state_for(alert.current_state)
    new_state = old_state.on_time_check(alert, now)
    if new_state is old_state:
        return False
    _commit_transition(session, alert, new_state.name, event_type="TIME_EXPIRE", payload={})
    return True


def apply_ack(session: Session, alert: Alert) -> bool:
    old_state = state_for(alert.current_state)
    new_state = old_state.on_ack(alert)
    if new_state is old_state:
        return False
    _commit_transition(session, alert, new_state.name, event_type="USER_ACK", payload={})
    return True


def apply_cancel(session: Session, alert: Alert) -> bool:
    old_state = state_for(alert.current_state)
    new_state = old_state.on_cancel(alert)
    if new_state is old_state:
        return False
    _commit_transition(session, alert, new_state.name, event_type="USER_CANCEL", payload={})
    return True


def evaluate_tick(session: Session, tick: Tick) -> list[Alert]:
    """Evaluates every armed/triggered alert on this tick's symbol against
    PRICE_TICK and TIME_EXPIRE, driving the state machine. Time checks piggy-
    back on tick arrival rather than a separate scheduler. Returns the alerts
    that just transitioned into Triggered, for the caller to broadcast."""
    alerts = session.scalars(
        select(Alert).where(
            Alert.symbol == tick.symbol,
            Alert.current_state.in_(["armed", "triggered"]),
        )
    ).all()

    newly_triggered: list[Alert] = []
    for alert in alerts:
        if alert.current_state == "armed":
            if apply_price_tick(session, alert, tick.price):
                if alert.current_state == "triggered":
                    newly_triggered.append(alert)
                continue
            apply_time_check(session, alert, tick.occurred_at)
        elif alert.current_state == "triggered":
            apply_time_check(session, alert, tick.occurred_at)

    return newly_triggered
