from app.config import HOLD_TTL_SECONDS
from app.db import get_pool


def hold_seat(seat_id: int, user_id: str) -> bool:
    """
    Try to put a hold on a seat. Returns True if this call won the seat,
    False if someone else already holds/booked it.

    The availability check and the mutation are one statement, so there is no
    window between reading the status and writing it. Postgres serializes
    concurrent writers to the same row, so exactly one caller sees rowcount 1.
    """
    with get_pool().connection() as conn:
        cur = conn.execute(
            """
            UPDATE event_seats
            SET status = 'held',
                held_by = %s,
                held_until = now() + make_interval(secs => %s)
            WHERE id = %s AND (status = 'available' OR (status = 'held' AND held_until < now()))
            """,
            (user_id, HOLD_TTL_SECONDS, seat_id),
        )
        return cur.rowcount == 1


def confirm_seat(seat_id: int, user_id: str, idempotency_key: str) -> dict:
    """
    Turn a live hold into a booking.

    Retries are safe: replaying the same idempotency key returns the original
    outcome instead of erroring or booking a second time.
    """
    with get_pool().connection() as conn:
        # Atomic confirm: the hold must belong to this user, still be live,
        # and not already carry this idempotency key.
        cur = conn.execute(
            """
            UPDATE event_seats
            SET status = 'booked', idempotency_key = %s
            WHERE id = %s AND status = 'held' AND held_by = %s
              AND held_until >= now()
              AND idempotency_key IS DISTINCT FROM %s
            """,
            (idempotency_key, seat_id, user_id, idempotency_key),
        )
        if cur.rowcount == 1:
            return {"confirmed": True, "replay": False}

        # Didn't update: either a replay of an already-processed key, or a
        # genuine failure (expired hold, wrong user, seat not held).
        row = conn.execute(
            "SELECT status, idempotency_key FROM event_seats WHERE id = %s",
            (seat_id,),
        ).fetchone()
        if row and row[1] == idempotency_key:
            return {"confirmed": row[0] == "booked", "replay": True}
        return {"confirmed": False, "replay": False}


def get_seats() -> list[dict]:
    """Current state of all seats; expired holds are reported as available."""
    with get_pool().connection() as conn:
        rows = conn.execute(
            """
            SELECT id,
                   CASE WHEN status = 'held' AND held_until < now()
                        THEN 'available' ELSE status END
            FROM event_seats
            ORDER BY id
            """
        ).fetchall()
        return [{"seat_id": r[0], "status": r[1]} for r in rows]
