from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from app.db import Base
from app.main import app
from app.routes.alerts import get_session


def _override_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'alerts_routes.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)

    def _get_session():
        with TestSession() as session:
            yield session

    return _get_session


def test_create_list_ack_and_cancel_alert_end_to_end(tmp_path):
    app.dependency_overrides[get_session] = _override_session(tmp_path)
    try:
        with TestClient(app) as client:
            future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

            create_resp = client.post(
                "/alerts",
                json={
                    "symbol": "aapl",
                    "threshold": 150.0,
                    "direction": "above",
                    "expires_at": future,
                    "ack_window_seconds": 60,
                },
            )
            assert create_resp.status_code == 201
            alert = create_resp.json()
            assert alert["symbol"] == "AAPL"
            assert alert["current_state"] == "armed"

            list_resp = client.get("/alerts")
            assert list_resp.status_code == 200
            assert len(list_resp.json()) == 1

            cancel_resp = client.post(f"/alerts/{alert['id']}/cancel")
            assert cancel_resp.status_code == 200
            assert cancel_resp.json()["current_state"] == "cancelled"
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_ack_on_unknown_alert_returns_404(tmp_path):
    app.dependency_overrides[get_session] = _override_session(tmp_path)
    try:
        with TestClient(app) as client:
            response = client.post("/alerts/999/ack")
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 404
