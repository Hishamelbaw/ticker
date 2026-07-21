from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.alerts.engine import apply_ack, apply_cancel, apply_price_tick, evaluate_tick
from app.db import Base
from app.generator import Tick
from app.models import Alert, EventLog


def _session_factory(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'alerts.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _make_alert(session, **overrides) -> Alert:
    defaults = dict(
        symbol="AAPL",
        threshold=150.0,
        direction="above",
        expires_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
        ack_window_seconds=60,
        current_state="armed",
    )
    defaults.update(overrides)
    alert = Alert(**defaults)
    session.add(alert)
    session.commit()
    session.refresh(alert)
    return alert


def _events_for(session, alert_id: int) -> list[EventLog]:
    return list(
        session.scalars(
            select(EventLog)
            .where(EventLog.entity_type == "alert", EventLog.entity_id == str(alert_id))
            .order_by(EventLog.id)
        ).all()
    )


def test_price_tick_that_crosses_threshold_transitions_and_logs_event(tmp_path):
    Session = _session_factory(tmp_path)
    with Session() as session:
        alert = _make_alert(session)

        transitioned = apply_price_tick(session, alert, 151.0)

        assert transitioned is True
        assert alert.current_state == "triggered"
        events = _events_for(session, alert.id)
        assert len(events) == 1
        assert events[0].event_type == "PRICE_TICK"
        assert events[0].entity_type == "alert"


def test_price_tick_below_threshold_does_not_transition_or_log(tmp_path):
    Session = _session_factory(tmp_path)
    with Session() as session:
        alert = _make_alert(session)

        transitioned = apply_price_tick(session, alert, 100.0)

        assert transitioned is False
        assert alert.current_state == "armed"
        assert _events_for(session, alert.id) == []


def test_ack_on_armed_alert_is_illegal_and_produces_no_event(tmp_path):
    Session = _session_factory(tmp_path)
    with Session() as session:
        alert = _make_alert(session)

        transitioned = apply_ack(session, alert)

        assert transitioned is False
        assert alert.current_state == "armed"
        assert _events_for(session, alert.id) == []


def test_cancel_on_armed_alert_transitions_and_logs_event(tmp_path):
    Session = _session_factory(tmp_path)
    with Session() as session:
        alert = _make_alert(session)

        transitioned = apply_cancel(session, alert)

        assert transitioned is True
        assert alert.current_state == "cancelled"
        events = _events_for(session, alert.id)
        assert len(events) == 1
        assert events[0].event_type == "USER_CANCEL"


def test_ack_on_triggered_alert_transitions_and_logs_event(tmp_path):
    Session = _session_factory(tmp_path)
    with Session() as session:
        alert = _make_alert(session, current_state="triggered", triggered_at=datetime.now(timezone.utc))

        transitioned = apply_ack(session, alert)

        assert transitioned is True
        assert alert.current_state == "acknowledged"
        events = _events_for(session, alert.id)
        assert len(events) == 1
        assert events[0].event_type == "USER_ACK"


def test_evaluate_tick_triggers_matching_armed_alerts_and_ignores_other_symbols(tmp_path):
    Session = _session_factory(tmp_path)
    with Session() as session:
        matching = _make_alert(session, symbol="AAPL", threshold=150.0, direction="above")
        other_symbol = _make_alert(session, symbol="GOOG", threshold=150.0, direction="above")

        tick = Tick(symbol="AAPL", price=151.0, occurred_at=datetime.now(timezone.utc))
        triggered = evaluate_tick(session, tick)

        assert [a.id for a in triggered] == [matching.id]
        session.refresh(matching)
        session.refresh(other_symbol)
        assert matching.current_state == "triggered"
        assert other_symbol.current_state == "armed"


def test_evaluate_tick_expires_armed_alert_past_its_expiry(tmp_path):
    Session = _session_factory(tmp_path)
    with Session() as session:
        alert = _make_alert(session, expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc))

        tick = Tick(symbol="AAPL", price=100.0, occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        evaluate_tick(session, tick)

        session.refresh(alert)
        assert alert.current_state == "expired"
        events = _events_for(session, alert.id)
        assert events[-1].event_type == "TIME_EXPIRE"
