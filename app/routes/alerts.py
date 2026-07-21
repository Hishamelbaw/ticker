from __future__ import annotations

from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts.engine import apply_ack, apply_cancel
from app.db import SessionLocal
from app.models import Alert
from app.schemas import AlertCreate, AlertRead

router = APIRouter(prefix="/alerts", tags=["alerts"])


def get_session() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session


@router.post("", response_model=AlertRead, status_code=201)
def create_alert(payload: AlertCreate, session: Session = Depends(get_session)) -> Alert:
    alert = Alert(
        symbol=payload.symbol.upper(),
        threshold=payload.threshold,
        direction=payload.direction,
        expires_at=payload.expires_at,
        ack_window_seconds=payload.ack_window_seconds,
        current_state="armed",
    )
    session.add(alert)
    session.commit()
    session.refresh(alert)
    return alert


@router.get("", response_model=list[AlertRead])
def list_alerts(session: Session = Depends(get_session)) -> list[Alert]:
    return list(session.scalars(select(Alert).order_by(Alert.id)).all())


def _get_or_404(session: Session, alert_id: int) -> Alert:
    alert = session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    return alert


@router.post("/{alert_id}/ack", response_model=AlertRead)
def ack_alert(alert_id: int, session: Session = Depends(get_session)) -> Alert:
    alert = _get_or_404(session, alert_id)
    apply_ack(session, alert)
    session.refresh(alert)
    return alert


@router.post("/{alert_id}/cancel", response_model=AlertRead)
def cancel_alert(alert_id: int, session: Session = Depends(get_session)) -> Alert:
    alert = _get_or_404(session, alert_id)
    apply_cancel(session, alert)
    session.refresh(alert)
    return alert
