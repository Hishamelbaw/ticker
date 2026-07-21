import json
from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.audit.event_log import append_event
from app.db import Base
from app.models import EventLog


def _engine_for(db_path):
    return create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})


def test_append_event_persists_to_disk_and_is_readable_from_a_new_connection(tmp_path):
    db_path = tmp_path / "audit.db"
    write_engine = _engine_for(db_path)
    Base.metadata.create_all(bind=write_engine)
    WriteSession = sessionmaker(bind=write_engine)

    with WriteSession() as session:
        append_event(
            session,
            entity_type="tick",
            entity_id="AAPL",
            event_type="tick",
            payload={"price": 100.0},
            occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    write_engine.dispose()

    # A brand-new engine/connection reading the same file proves the row
    # actually reached disk, not just the original session's identity map.
    read_engine = _engine_for(db_path)
    ReadSession = sessionmaker(bind=read_engine)
    with ReadSession() as session:
        rows = session.scalars(select(EventLog)).all()

    assert len(rows) == 1
    assert rows[0].entity_type == "tick"
    assert rows[0].entity_id == "AAPL"
    assert rows[0].event_type == "tick"
    assert json.loads(rows[0].payload_json) == {"price": 100.0}


def test_events_are_queryable_in_chronological_order(tmp_path):
    db_path = tmp_path / "audit.db"
    engine = _engine_for(db_path)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    with Session() as session:
        append_event(
            session, entity_type="tick", entity_id="AAPL", event_type="tick",
            payload={"price": 1}, occurred_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        )
        append_event(
            session, entity_type="tick", entity_id="AAPL", event_type="tick",
            payload={"price": 2}, occurred_at=datetime(2026, 1, 1, 0, 0, 2, tzinfo=timezone.utc),
        )
        append_event(
            session, entity_type="tick", entity_id="AAPL", event_type="tick",
            payload={"price": 3}, occurred_at=datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
        )

        # Insertion order was 1, 2, 3 -- querying by occurred_at must return
        # chronological order (1, 3, 2), not insertion order.
        rows = session.scalars(select(EventLog).order_by(EventLog.occurred_at)).all()

    prices = [json.loads(row.payload_json)["price"] for row in rows]
    assert prices == [1, 3, 2]
