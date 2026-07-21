import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.alerts import engine
from app.audit.reconstruct import reconstruct_alert_state
from app.db import Base


def _session_factory(tmp_path):
    engine_obj = create_engine(
        f"sqlite:///{tmp_path / 'reconstruct.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine_obj)
    return sessionmaker(bind=engine_obj, expire_on_commit=False)


def test_reconstruct_returns_none_before_the_alert_existed(tmp_path):
    Session = _session_factory(tmp_path)
    with Session() as session:
        alert = engine.create_alert(
            session,
            symbol="AAPL",
            threshold=150.0,
            direction="above",
            expires_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
            ack_window_seconds=60,
        )
        before_creation = alert.created_at - timedelta(seconds=1)

        assert reconstruct_alert_state(session, alert.id, before_creation) is None


def test_reconstruct_returns_armed_right_after_creation_before_any_transition(tmp_path):
    Session = _session_factory(tmp_path)
    with Session() as session:
        alert = engine.create_alert(
            session,
            symbol="AAPL",
            threshold=150.0,
            direction="above",
            expires_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
            ack_window_seconds=60,
        )

        assert reconstruct_alert_state(session, alert.id, alert.created_at) == "armed"


def test_reconstruct_returns_the_state_as_of_a_point_between_two_real_transitions(tmp_path):
    Session = _session_factory(tmp_path)
    with Session() as session:
        alert = engine.create_alert(
            session,
            symbol="AAPL",
            threshold=150.0,
            direction="above",
            expires_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
            ack_window_seconds=60,
        )

        # Transition 1: a real PRICE_TICK-driven transition, armed -> triggered.
        assert engine.apply_price_tick(session, alert, 151.0) is True
        assert alert.current_state == "triggered"

        time.sleep(0.05)
        as_of_between = datetime.now(timezone.utc)
        time.sleep(0.05)

        # Transition 2: a real USER_ACK-driven transition, triggered -> acknowledged.
        assert engine.apply_ack(session, alert) is True
        assert alert.current_state == "acknowledged"

        reconstructed = reconstruct_alert_state(session, alert.id, as_of_between)

    # The proof: replaying to a point between the two transitions returns the
    # state as of that point, not the alert's current (post-ack) state.
    assert reconstructed == "triggered"
    assert reconstructed != alert.current_state


def test_reconstruct_matches_current_state_when_as_of_is_now(tmp_path):
    Session = _session_factory(tmp_path)
    with Session() as session:
        alert = engine.create_alert(
            session,
            symbol="AAPL",
            threshold=150.0,
            direction="above",
            expires_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
            ack_window_seconds=60,
        )
        engine.apply_price_tick(session, alert, 151.0)
        engine.apply_ack(session, alert)

        reconstructed = reconstruct_alert_state(session, alert.id, datetime.now(timezone.utc))

    assert reconstructed == alert.current_state == "acknowledged"
