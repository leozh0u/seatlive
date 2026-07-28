from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.config import DATABASE_URL, SEAT_COUNT
from app.main import app, limiter

SCHEMA = Path(__file__).parent.parent / "schema.sql"


@pytest.fixture(scope="session", autouse=True)
def schema():
    """Make sure the table exists before any test touches it."""
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute(SCHEMA.read_text())


@pytest.fixture
def seat_id():
    """Reseed the demo event and hand back the first seat, status available."""
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute("DELETE FROM event_seats WHERE event_id = 1")
        conn.execute(
            """
            INSERT INTO event_seats (event_id, seat_label)
            SELECT 1, 'A' || n FROM generate_series(1, %s) AS n
            """,
            (SEAT_COUNT,),
        )
        row = conn.execute(
            "SELECT id FROM event_seats WHERE event_id = 1 ORDER BY id LIMIT 1"
        ).fetchone()
        return row[0]


@pytest.fixture
def client():
    """
    App under test with rate limiting off.

    The limiter keys on client IP and every request here comes from the same
    one, so leaving it on would make unrelated tests fail on request eleven.
    test_api.py turns it back on for the one test that checks it works.
    """
    limiter.enabled = False
    with TestClient(app) as test_client:
        yield test_client
    limiter.enabled = True


def expire_hold(seat_id: int):
    """Backdate a live hold so it reads as expired."""
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute(
            "UPDATE event_seats SET held_until = now() - interval '1 minute' WHERE id = %s",
            (seat_id,),
        )
