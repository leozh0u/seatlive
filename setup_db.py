"""Apply the schema and seed the demo event's seats."""

from pathlib import Path

import psycopg

from app.config import DATABASE_URL, SEAT_COUNT

SCHEMA = Path(__file__).parent / "schema.sql"


def main():
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(SCHEMA.read_text())
        # Stable ids 1..SEAT_COUNT so the demo frontend and the load tests can
        # address seats without looking them up first.
        conn.execute("TRUNCATE event_seats RESTART IDENTITY")
        conn.execute(
            """
            INSERT INTO event_seats (event_id, seat_label)
            SELECT 1, 'A' || n FROM generate_series(1, %s) AS n
            """,
            (SEAT_COUNT,),
        )
    print(f"Schema applied, {SEAT_COUNT} demo seats seeded.")


if __name__ == "__main__":
    main()
