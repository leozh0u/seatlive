# SeatLive

[![CI](https://github.com/leozh0u/seatlive/actions/workflows/ci.yml/badge.svg)](https://github.com/leozh0u/seatlive/actions/workflows/ci.yml)

Real-time event seat-booking platform. Solves the core hard problem in any booking system: preventing double-booked seats under concurrent load, using an atomic conditional UPDATE in Postgres rather than application-level locking.

## Architecture

```
┌──────────────┐      HTTP       ┌──────────────┐
│  React (5173) │ ───────────────▶│ FastAPI (8000)│
└──────┬───────┘                 └──────┬───────┘
       │  WebSocket                     │
       │                          ┌─────▼─────┐
       │                          │ PostgreSQL │  ← atomic UPDATE,
       │                          │  (5432)    │    row-level locking
       │                          └─────┬─────┘
       │                                │
       │                          ┌─────▼─────┐
       └─────────────────────────▶│   Redis    │  pub/sub broadcast
          seat_updates channel    │  (6379)    │
                                  └────────────┘
```

Flow: client holds a seat → atomic UPDATE wins or loses → winner publishes to Redis → each server instance runs a single background subscriber that broadcasts to its own connected clients → all browsers update instantly, no polling.

## Core correctness guarantee

```sql
UPDATE event_seats
SET status = 'held', held_by = %s, held_until = now() + interval '5 minutes'
WHERE id = %s AND (status = 'available' OR (status = 'held' AND held_until < now()))
```

The check and the mutation are the same statement, so there is no gap between "is it available?" and "mark it held." Postgres serializes concurrent writes to the same row via row-level locking, so exactly one concurrent request wins. Verified under 50-thread `threading.Barrier` load in [`tests/test_concurrency.py`](tests/test_concurrency.py).

## Stack

- **Backend:** Python 3.12+, FastAPI, psycopg (pooled via psycopg_pool), ruff
- **Database:** PostgreSQL
- **Real-time:** Redis pub/sub, WebSockets
- **Frontend:** React + Vite
- **Infra:** Docker Compose, GitHub Actions CI, Sentry error monitoring
- **Load testing:** Locust

## Layout

```
app/        config, connection pool, the seat queries, the FastAPI app
tests/      concurrency tests against Postgres, plus HTTP and websocket tests
frontend/   React demo: hold a seat, confirm it, watch other tabs update
schema.sql  one table
locustfile.py
```

## Local setup

The whole stack, schema included, comes up with one command:

```bash
docker compose up
```

That serves the API on `:8000` against Postgres on `:5433` and Redis on `:6380`.

To run the backend directly instead, start Postgres and Redis yourself (Postgres.app and
`brew services start redis` work fine), then:

```bash
git clone https://github.com/leozh0u/seatlive.git
cd seatlive
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python setup_db.py
uvicorn app.main:app --reload
```

The frontend is separate:

```bash
npm install --prefix frontend
npm run dev --prefix frontend
```

Backend on `:8000`, frontend on `:5173`. Point the frontend somewhere else with
`VITE_API_URL`. Open it in two tabs to watch one tab's hold land in the other.

Configuration is all environment variables, read in [`app/config.py`](app/config.py):
`DATABASE_URL`, `REDIS_URL`, `CORS_ORIGINS`, `HOLD_TTL_SECONDS`, `SEAT_COUNT`, `SENTRY_DSN`.

## API

| Endpoint | Method | Description |
|---|---|---|
| `/seats` | GET | Current status of all seats (expired holds reported as available) |
| `/seats/{seat_id}/hold` | POST | Atomically hold a seat (rate-limited, validated) |
| `/seats/{seat_id}/confirm` | POST | Convert a hold into a booking, idempotent via client-supplied key |
| `/healthz` | GET | Liveness check |
| `/ws` | WebSocket | Real-time seat status broadcast |

## Testing

```bash
pytest
```

Needs Postgres and Redis running, same as the app. CI runs both as service containers.

The concurrency tests cover single-winner correctness under 50 threads, expired-hold
reclamation under the same contention, and repeated confirms of one idempotency key
booking the seat exactly once. The API tests cover input validation, the hold/confirm
flow over HTTP, the rate limiter returning 429, and a hold travelling out through Redis
to a connected websocket.

## Load testing

See [`LOAD_TESTING.md`](./LOAD_TESTING.md) for real Locust results: 4459 requests, 0 failures, 18.7 req/s, p95 570ms.

## Known limitations

- Confirm idempotency key is not scoped per user: a key collision across two different users' clients would leak one confirm result to the other. Low risk with UUIDs, real tradeoff.
- DB calls are synchronous (psycopg, pooled) inside async endpoints, briefly blocking the event loop under load. An async driver would remove this.
- No structured logging yet. Sentry covers unhandled exceptions but there's no request/response audit trail.
