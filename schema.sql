CREATE TABLE IF NOT EXISTS event_seats (
  id          BIGSERIAL PRIMARY KEY,
  event_id    BIGINT NOT NULL,
  seat_label  TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'available'
              CHECK (status IN ('available','held','booked')),
  held_by     TEXT,
  held_until  TIMESTAMPTZ,
  idempotency_key TEXT,
  UNIQUE (event_id, seat_label)
);

-- Every hold and confirm targets one seat by primary key, so the lookup is
-- already covered. This index keeps the GET /seats listing on one event cheap
-- once more than one event exists.
CREATE INDEX IF NOT EXISTS event_seats_event_id_idx ON event_seats (event_id);
