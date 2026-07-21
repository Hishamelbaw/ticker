from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EventLog


def reconstruct_alert_state(session: Session, alert_id: int, as_of: datetime) -> str | None:
    """Replays this alert's EventLog rows up to and including as_of, in
    chronological order, and returns the state that resulted -- entirely
    independent of the current materialized Alert row.

    Returns None if the alert had not been created yet as of as_of.
    """
    events = session.scalars(
        select(EventLog)
        .where(
            EventLog.entity_type == "alert",
            EventLog.entity_id == str(alert_id),
            EventLog.occurred_at <= as_of,
        )
        .order_by(EventLog.occurred_at, EventLog.id)
    ).all()

    state: str | None = None
    for event in events:
        state = json.loads(event.payload_json)["new_state"]
    return state
