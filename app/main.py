import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.generator import TickGenerator, run_generator

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    generator_task = asyncio.create_task(run_generator(TickGenerator()))
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


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_echo(websocket: WebSocket):
    origin = websocket.headers.get("origin")
    if origin is not None and origin not in settings.allowed_origins_list:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    try:
        while True:
            message = await websocket.receive_text()
            await websocket.send_text(message)
    except WebSocketDisconnect:
        pass
