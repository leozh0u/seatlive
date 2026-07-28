import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://localhost:5432/postgres",
)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost")

SENTRY_DSN = os.environ.get("SENTRY_DSN")

# Origins allowed to call the API. The demo frontend runs on Vite's dev server;
# override with a comma-separated list when deploying somewhere real.
CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]

# How long a hold survives before anyone else can take the seat.
HOLD_TTL_SECONDS = int(os.environ.get("HOLD_TTL_SECONDS", "300"))

# Seats created by setup_db.py for the demo event.
SEAT_COUNT = int(os.environ.get("SEAT_COUNT", "8"))

# Redis channel every API instance subscribes to.
SEAT_UPDATES_CHANNEL = "seat_updates"
