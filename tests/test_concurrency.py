"""The core correctness claim: one seat, many racing callers, exactly one winner."""

import threading
from concurrent.futures import ThreadPoolExecutor

from app.seats import confirm_seat, get_seats, hold_seat
from tests.conftest import expire_hold

CONTENDERS = 50


def race_to_hold(seat_id: int) -> list[bool]:
    """Fire CONTENDERS threads at one seat, released together by a barrier."""
    barrier = threading.Barrier(CONTENDERS)

    def try_hold(user_id: str) -> bool:
        barrier.wait()
        return hold_seat(seat_id, user_id)

    with ThreadPoolExecutor(max_workers=CONTENDERS) as executor:
        return list(executor.map(try_hold, [f"user{i}" for i in range(CONTENDERS)]))


def test_only_one_winner(seat_id):
    assert race_to_hold(seat_id).count(True) == 1


def test_expired_hold_reclaimed(seat_id):
    """A held seat past its TTL goes back up for grabs, still to exactly one caller."""
    assert hold_seat(seat_id, "old_user") is True
    expire_hold(seat_id)

    assert race_to_hold(seat_id).count(True) == 1


def test_expired_hold_reads_as_available(seat_id):
    assert hold_seat(seat_id, "userA") is True
    assert {s["seat_id"]: s["status"] for s in get_seats()}[seat_id] == "held"

    expire_hold(seat_id)
    assert {s["seat_id"]: s["status"] for s in get_seats()}[seat_id] == "available"


def test_confirm_idempotent(seat_id):
    hold_seat(seat_id, "userA")

    assert confirm_seat(seat_id, "userA", "key123") == {
        "confirmed": True,
        "replay": False,
    }
    assert confirm_seat(seat_id, "userA", "key123") == {
        "confirmed": True,
        "replay": True,
    }


def test_concurrent_confirms_book_once(seat_id):
    """Retrying the same confirm from several threads still books the seat once."""
    hold_seat(seat_id, "userA")
    barrier = threading.Barrier(CONTENDERS)

    def confirm(_):
        barrier.wait()
        return confirm_seat(seat_id, "userA", "same-key")

    with ThreadPoolExecutor(max_workers=CONTENDERS) as executor:
        results = list(executor.map(confirm, range(CONTENDERS)))

    # One caller does the write, the rest replay it. Nobody gets an error and
    # nobody books a second time.
    assert [r["replay"] for r in results].count(False) == 1
    assert all(r["confirmed"] for r in results)


def test_confirm_rejects_expired_hold(seat_id):
    hold_seat(seat_id, "userA")
    expire_hold(seat_id)

    assert confirm_seat(seat_id, "userA", "key123") == {
        "confirmed": False,
        "replay": False,
    }


def test_confirm_rejects_wrong_user(seat_id):
    hold_seat(seat_id, "userA")

    assert confirm_seat(seat_id, "userB", "key456") == {
        "confirmed": False,
        "replay": False,
    }


def test_confirm_rejects_seat_that_was_never_held(seat_id):
    assert confirm_seat(seat_id, "userA", "key789") == {
        "confirmed": False,
        "replay": False,
    }
