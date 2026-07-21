import time

from starlette.testclient import TestClient

from app.main import app
from app.messaging.connection_manager import manager


def _wait_until(predicate, timeout: float = 3.0, interval: float = 0.05) -> bool:
    deadline = time.time() + timeout
    result = False
    while time.time() < deadline:
        try:
            result = predicate()
        except RuntimeError:
            result = False
        if result:
            return True
        time.sleep(interval)
    return result


def test_two_concurrent_clients_only_receive_their_own_subscribed_symbols():
    with TestClient(app) as client:
        with client.websocket_connect("/ws?symbols=AAPL,GOOG") as ws_a:
            with client.websocket_connect("/ws?symbols=TSLA") as ws_b:
                ack_a = ws_a.receive_json()
                ack_b = ws_b.receive_json()
                assert set(ack_a["symbols"]) == {"AAPL", "GOOG"}
                assert set(ack_b["symbols"]) == {"TSLA"}

                ticks_a = [ws_a.receive_json() for _ in range(2)]
                ticks_b = [ws_b.receive_json() for _ in range(2)]

    symbols_a = {t["symbol"] for t in ticks_a}
    symbols_b = {t["symbol"] for t in ticks_b}

    assert symbols_a <= {"AAPL", "GOOG"}
    assert symbols_b == {"TSLA"}
    assert symbols_a  # confirm messages actually arrived, not just an empty subset


def test_client_disconnect_is_handled_cleanly_and_removes_the_subscriber():
    with TestClient(app) as client:
        with client.websocket_connect("/ws?symbols=AMZN") as ws:
            ws.receive_json()
            assert _wait_until(lambda: manager.subscriber_count("AMZN") >= 1)

        assert _wait_until(lambda: manager.subscriber_count("AMZN") == 0)

    # A subsequent request against the (still-live within this block) app must
    # not have crashed the server process as a result of the disconnect.
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
