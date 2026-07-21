import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.audit.event_log import append_event
from app.config import settings
from app.db import SessionLocal, init_db
from app.generator import Tick, TickGenerator, run_generator
from app.messaging.aggregator import Candle, CandleAggregator
from app.messaging.connection_manager import manager
from app.messaging.enricher import EnrichedTick, TickEnricher
from app.messaging.router import Event, EventType, MessageRouter
from app.routes.ws import router as ws_router

logging.basicConfig(level=logging.INFO)

router = MessageRouter()
enricher = TickEnricher()
aggregator = CandleAggregator()


def _serialize_tick(tick: EnrichedTick) -> dict[str, Any]:
    return {
        "topic": "ticks",
        "symbol": tick.symbol,
        "price": tick.price,
        "percent_change": tick.percent_change,
        "moving_average": tick.moving_average,
        "occurred_at": tick.occurred_at.isoformat(),
    }


def _serialize_candle(candle: Candle) -> dict[str, Any]:
    return {
        "topic": "candles",
        "symbol": candle.symbol,
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "window_start": candle.window_start.isoformat(),
        "window_end": candle.window_end.isoformat(),
    }


def _log_tick(tick: Tick) -> None:
    with SessionLocal() as session:
        append_event(
            session,
            entity_type="tick",
            entity_id=tick.symbol,
            event_type="tick",
            payload={"symbol": tick.symbol, "price": tick.price},
            occurred_at=tick.occurred_at,
        )


async def _handle_tick(event: Event) -> None:
    tick: Tick = event.payload
    await asyncio.to_thread(_log_tick, tick)

    enriched = enricher.enrich(tick)
    await manager.broadcast(tick.symbol, _serialize_tick(enriched))

    candle = aggregator.add_tick(tick)
    if candle is not None:
        await router.dispatch(Event(type=EventType.CANDLE_CLOSE, payload=candle))


async def _handle_candle_close(event: Event) -> None:
    candle: Candle = event.payload
    await manager.broadcast(candle.symbol, _serialize_candle(candle))


router.register(EventType.TICK, _handle_tick)
router.register(EventType.CANDLE_CLOSE, _handle_candle_close)


async def _on_tick(tick: Tick) -> None:
    await router.dispatch(Event(type=EventType.TICK, payload=tick))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    generator_task = asyncio.create_task(run_generator(TickGenerator(), _on_tick))
    try:
        yield
    finally:
        generator_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await generator_task


app = FastAPI(title="Ticker", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ws_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
