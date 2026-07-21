from app.messaging.connection_manager import ConnectionManager


class FakeWebSocket:
    def __init__(self, fail: bool = False) -> None:
        self.messages: list[dict] = []
        self._fail = fail

    async def send_json(self, message: dict) -> None:
        if self._fail:
            raise RuntimeError("connection is closed")
        self.messages.append(message)


async def test_broadcast_reaches_only_subscribers_of_that_symbol():
    manager = ConnectionManager()
    aapl_client = FakeWebSocket()
    tsla_client = FakeWebSocket()
    manager.connect(aapl_client, {"AAPL"})
    manager.connect(tsla_client, {"TSLA"})

    await manager.broadcast("AAPL", {"symbol": "AAPL", "price": 100.0})

    assert aapl_client.messages == [{"symbol": "AAPL", "price": 100.0}]
    assert tsla_client.messages == []


async def test_subscribe_adds_symbols_without_dropping_existing_ones():
    manager = ConnectionManager()
    client = FakeWebSocket()
    manager.connect(client, {"AAPL"})

    manager.subscribe(client, {"TSLA"})

    assert manager.subscriptions_for(client) == {"AAPL", "TSLA"}


async def test_unsubscribe_removes_only_the_requested_symbols():
    manager = ConnectionManager()
    client = FakeWebSocket()
    manager.connect(client, {"AAPL", "TSLA"})

    manager.unsubscribe(client, {"TSLA"})

    assert manager.subscriptions_for(client) == {"AAPL"}


async def test_disconnect_removes_subscriber_so_future_broadcasts_skip_it():
    manager = ConnectionManager()
    client = FakeWebSocket()
    manager.connect(client, {"AAPL"})

    manager.disconnect(client)
    await manager.broadcast("AAPL", {"symbol": "AAPL"})

    assert client.messages == []
    assert manager.subscriber_count("AAPL") == 0


async def test_broadcast_prunes_connections_that_error_on_send():
    manager = ConnectionManager()
    dead_client = FakeWebSocket(fail=True)
    live_client = FakeWebSocket()
    manager.connect(dead_client, {"AAPL"})
    manager.connect(live_client, {"AAPL"})

    await manager.broadcast("AAPL", {"symbol": "AAPL"})

    assert live_client.messages == [{"symbol": "AAPL"}]
    assert manager.subscriber_count("AAPL") == 1
