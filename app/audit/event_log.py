from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import EventLog


def append_event(
    session: Session,
    *,
    entity_type: str,
    entity_id: str,
    event_type: str,
    payload: dict[str, Any],
    occurred_at: datetime,
) -> EventLog:
    event = EventLog(
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        payload_json=json.dumps(payload),
        occurred_at=occurred_at,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event
