import pytest

from app.messaging.router import Event, EventType, MessageRouter


@pytest.mark.asyncio
async def test_dispatches_to_registered_handler_for_matching_type():
    router = MessageRouter()
    received = []

    async def handler(event: Event) -> None:
        received.append(event.payload)

    router.register(EventType.TICK, handler)
    await router.dispatch(Event(type=EventType.TICK, payload={"symbol": "AAPL"}))

    assert received == [{"symbol": "AAPL"}]


@pytest.mark.asyncio
async def test_ignores_event_types_with_no_registered_handler():
    router = MessageRouter()
    called = False

    async def handler(event: Event) -> None:
        nonlocal called
        called = True

    router.register(EventType.TICK, handler)
    await router.dispatch(Event(type=EventType.ALERT_CHECK, payload=None))

    assert called is False


@pytest.mark.asyncio
async def test_dispatches_to_multiple_handlers_in_registration_order():
    router = MessageRouter()
    calls: list[str] = []

    async def first(event: Event) -> None:
        calls.append("first")

    async def second(event: Event) -> None:
        calls.append("second")

    router.register(EventType.CANDLE_CLOSE, first)
    router.register(EventType.CANDLE_CLOSE, second)
    await router.dispatch(Event(type=EventType.CANDLE_CLOSE, payload=None))

    assert calls == ["first", "second"]
