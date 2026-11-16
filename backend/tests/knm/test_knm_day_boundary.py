# KNM FORK ONLY - NEVER SEND UPSTREAM
"""The daily cap rolls over at America/New_York midnight (DST-aware), not UTC midnight."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from knm import store

NY = ZoneInfo("America/New_York")


def ny(y, mo, d, h=0, mi=0, s=0):
    return datetime(y, mo, d, h, mi, s, tzinfo=NY).timestamp()


@pytest.mark.parametrize("y,mo,d", [(2026, 1, 15), (2026, 7, 15)])  # EST, EDT
def test_day_start_is_ny_midnight_around_the_boundary(y, mo, d):
    mid = ny(y, mo, d)
    assert store.day_start(mid) == mid
    assert store.day_start(mid + 1) == mid
    assert store.day_start(mid + 86399) == mid
    assert store.day_start(mid - 1) == ny(y, mo, d - 1)
    assert store.day_start(ny(y, mo, d, 12)) == mid


def test_day_start_not_utc_midnight():
    # 9 pm EST Jan 14 is already Jan 15 UTC, but still NY Jan 14
    assert store.day_start(ny(2026, 1, 14, 21)) == ny(2026, 1, 14)


def test_spring_forward_day_is_23_hours():
    mid, nxt = ny(2026, 3, 8), ny(2026, 3, 9)
    assert nxt - mid == 23 * 3600
    assert store.day_start(nxt - 1) == mid
    assert store.day_start(nxt) == nxt


def test_fall_back_day_is_25_hours():
    mid, nxt = ny(2026, 11, 1), ny(2026, 11, 2)
    assert nxt - mid == 25 * 3600
    assert store.day_start(nxt - 1) == mid
    assert store.day_start(mid + 24 * 3600) == mid     # the repeated hour is still the same day
    assert store.day_start(nxt) == nxt


def _req(created_at, username="bob"):
    store.write(
        "INSERT INTO knm_requests (server_id, user_id, username, kind, title, item_kind, item_id, status, "
        "created_at, updated_at) VALUES (1,2,?,?,?,?,?,?,?,?)",
        (username, "movie", "T", "movie", 1, "queued", created_at, created_at))


@pytest.mark.parametrize("username", ["bob", None])
def test_used_today_rolls_over_at_ny_midnight(db, username):
    _req(ny(2026, 1, 14, 21), "bob")          # 9 pm NY, Jan 14
    before_midnight = ny(2026, 1, 14, 23, 59, 59)
    after_midnight = ny(2026, 1, 15, 0, 0, 1)
    assert store.used_today(1, 2, now=before_midnight, username=username) == 1
    assert store.used_today(1, 2, now=after_midnight, username=username) == 0
