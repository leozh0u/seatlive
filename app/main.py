import asyncio
import json
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
import sentry_sdk
from fastapi import FastAPI, Path, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.config import CORS_ORIGINS, REDIS_URL, SEAT_UPDATES_CHANNEL, SENTRY_DSN
from app.db import close_pool
from app.seats import confirm_seat, get_seats, hold_seat

if SENTRY_DSN:
    sentry_sdk.init(dsn=SENTRY_DSN)

USER_ID = Query(..., min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
SEAT_ID = Path(..., ge=1)


class ConnectionManager:
    """Tracks the websockets connected to *this* process."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        dead = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                dead.append(connection)
        for connection in dead:
            self.disconnect(connection)


manager = ConnectionManager()


async def redis_subscriber(redis: aioredis.Redis):
    """Single subscription per server process; fans out to local websockets."""
    pubsub = redis.pubsub()
    await pubsub.subscribe(SEAT_UPDATES_CHANNEL)
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                await manager.broadcast(message["data"].decode())
    finally:
        await pubsub.aclose()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = aioredis.from_url(REDIS_URL)
    subscriber_task = asyncio.create_task(redis_subscriber(app.state.redis))
    try:
        yield
    finally:
        subscriber_task.cancel()
        await asyncio.gather(subscriber_task, return_exceptions=True)
        await app.state.redis.aclose()
        close_pool()


app = FastAPI(title="SeatLive", lifespan=lifespan)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def publish(request: Request, seat_id: int, status: str, user_id: str):
    """Tell every API instance about a seat that changed hands."""
    await request.app.state.redis.publish(
        SEAT_UPDATES_CHANNEL,
        json.dumps({"seat_id": seat_id, "status": status, "user_id": user_id}),
    )


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/seats")
async def seats():
    return get_seats()


@app.post("/seats/{seat_id}/hold")
@limiter.limit("10/minute")
async def hold(request: Request, seat_id: int = SEAT_ID, user_id: str = USER_ID):
    won = hold_seat(seat_id, user_id)
    if won:
        await publish(request, seat_id, "held", user_id)
    return {"held": won}


@app.post("/seats/{seat_id}/confirm")
@limiter.limit("10/minute")
async def confirm(
    request: Request,
    seat_id: int = SEAT_ID,
    user_id: str = USER_ID,
    idempotency_key: str = Query(..., min_length=1, max_length=200),
):
    result = confirm_seat(seat_id, user_id, idempotency_key)
    if result["confirmed"] and not result["replay"]:
        await publish(request, seat_id, "booked", user_id)
    return result


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # We never expect client messages; receiving is how we detect disconnects.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)
