"""HTTP and websocket behaviour: validation, the hold/confirm flow, live broadcast."""

import json

from app.main import limiter


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_seats_listing(client, seat_id):
    seats = client.get("/seats").json()

    assert len(seats) == 8
    assert all(seat["status"] == "available" for seat in seats)


def test_hold_then_confirm(client, seat_id):
    held = client.post(f"/seats/{seat_id}/hold", params={"user_id": "alice"})
    assert held.json() == {"held": True}

    confirmed = client.post(
        f"/seats/{seat_id}/confirm",
        params={"user_id": "alice", "idempotency_key": "abc-123"},
    )
    assert confirmed.json() == {"confirmed": True, "replay": False}

    statuses = {s["seat_id"]: s["status"] for s in client.get("/seats").json()}
    assert statuses[seat_id] == "booked"


def test_second_hold_loses(client, seat_id):
    client.post(f"/seats/{seat_id}/hold", params={"user_id": "alice"})

    lost = client.post(f"/seats/{seat_id}/hold", params={"user_id": "bob"})
    assert lost.json() == {"held": False}


def test_retried_confirm_replays(client, seat_id):
    client.post(f"/seats/{seat_id}/hold", params={"user_id": "alice"})
    params = {"user_id": "alice", "idempotency_key": "retry-me"}

    first = client.post(f"/seats/{seat_id}/confirm", params=params)
    second = client.post(f"/seats/{seat_id}/confirm", params=params)

    assert first.json() == {"confirmed": True, "replay": False}
    assert second.json() == {"confirmed": True, "replay": True}


def test_rejects_bad_user_id(client, seat_id):
    """user_id feeds a SQL parameter and a broadcast payload, so it is validated."""
    bad = client.post(f"/seats/{seat_id}/hold", params={"user_id": "robert'); drop--"})
    assert bad.status_code == 422


def test_rejects_missing_user_id(client, seat_id):
    assert client.post(f"/seats/{seat_id}/hold").status_code == 422


def test_rejects_seat_id_below_range(client):
    assert client.post("/seats/0/hold", params={"user_id": "alice"}).status_code == 422


def test_unknown_seat_is_not_held(client, seat_id):
    """An id that matches no row simply wins nothing, rather than erroring."""
    missing = client.post("/seats/999999/hold", params={"user_id": "alice"})

    assert missing.status_code == 200
    assert missing.json() == {"held": False}


def test_hold_broadcasts_over_websocket(client, seat_id):
    """
    End to end: hold -> Redis publish -> the process's subscriber -> this socket.

    This is the path that keeps every browser in sync without polling, so it is
    worth testing through the real Redis rather than a stub.
    """
    with client.websocket_connect("/ws") as ws:
        client.post(f"/seats/{seat_id}/hold", params={"user_id": "alice"})

        message = json.loads(ws.receive_text())

    assert message == {"seat_id": seat_id, "status": "held", "user_id": "alice"}


def test_rate_limit_returns_429(client, seat_id):
    """The limiter is off for the other tests; check it actually bites."""
    limiter.enabled = True
    try:
        codes = [
            client.post(f"/seats/{seat_id}/hold", params={"user_id": "alice"}).status_code
            for _ in range(12)
        ]
    finally:
        limiter.enabled = False
        limiter.reset()

    assert codes[:10] == [200] * 10
    assert codes[10:] == [429, 429]
