from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class EventLog(Base):
    """Append-only audit trail: every tick ingested and every alert state
    transition is a row here. Current state elsewhere is a materialized view;
    this table is the source of truth events replay from."""

    __tablename__ = "event_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(50), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class Alert(Base):
    """Materialized current-state view of an alert. current_state is always
    derivable by replaying EventLog rows where entity_type="alert" and
    entity_id=str(id); this row is a fast-read cache of that replay."""

    __tablename__ = "alert"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # "above" | "below"
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ack_window_seconds: Mapped[int] = mapped_column(nullable=False, default=300)
    current_state: Mapped[str] = mapped_column(String(20), nullable=False, default="armed")
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
