# KNM FORK ONLY - NEVER SEND UPSTREAM
"""Allow-list and daily cap are keyed on the case-insensitive trimmed username, not server/user id."""

import pytest

import vod_db
from knm import store
from test_knm_api import KEYS, H, _movie, allow, client, post  # noqa: F401  (client is a fixture)


@pytest.fixture()
def two(client, monkeypatch):
    """Same person (username 'bob') known under a different server and user id."""
    sid2 = vod_db.create_dispatcharr_connection("Main", "http://other.example:9191", "STORED2")
    monkeypatch.setitem(KEYS, "k-bob2", {"id": 77, "username": " Bob ", "user_level": 1})
    client.server2 = sid2
    return client


def me(c, key, server):
    return c.get("/api/knm/me", headers=H(key, server)).json()


def test_allow_on_one_server_applies_on_another_and_case_insensitive(two):
    allow(two, user_id=2, username="bob", cap=3)
    r = me(two, "k-bob2", two.server2)
    assert r["allowed"] is True and r["cap"] == 3


def test_not_on_list_still_denied(two):
    allow(two, user_id=3, username="amy")
    assert me(two, "k-bob2", two.server2)["allowed"] is False


def test_admin_always_allowed(two):
    assert me(two, "k-admin", two.server_id)["allowed"] is True


def test_put_upserts_by_username_one_entry_for_all_servers(two):
    allow(two, user_id=2, username="bob", cap=3)
    body = {"entries": [{"server_id": two.server2, "user_id": 77, "username": "BOB", "allowed": True, "daily_cap": 4}]}
    assert two.put("/api/knm/allowlist", json=body, headers=H("k-admin", two.server_id)).status_code == 200
    ents = two.get("/api/knm/allowlist", headers=H("k-admin", two.server_id)).json()["entries"]
    assert len(ents) == 1 and ents[0]["daily_cap"] == 4
    assert me(two, "k-bob", two.server_id)["cap"] == 4


def test_disallow_by_username_covers_every_server(two):
    allow(two, user_id=2, username="bob")
    two.put("/api/knm/allowlist", headers=H("k-admin", two.server_id), json={"entries": [
        {"server_id": two.server2, "user_id": 77, "username": "bob", "allowed": False}]})
    assert me(two, "k-bob", two.server_id)["allowed"] is False
    assert me(two, "k-bob2", two.server2)["allowed"] is False


def test_legacy_duplicate_rows_allowed_if_any_allowed_and_latest_cap(two):
    ins = "INSERT INTO knm_allowlist (server_id,user_id,username,allowed,daily_cap,updated_at) VALUES (?,?,?,?,?,?)"
    store.write(ins, (two.server_id, 2, "bob", 0, 9, 100.0))
    store.write(ins, (two.server2, 77, "Bob", 1, 2, 200.0))
    r = me(two, "k-bob", two.server_id)
    assert r["allowed"] is True and r["cap"] == 2


def test_daily_cap_counts_across_servers_by_username(two, db):
    for i in range(3):
        _movie(db, name=f"M{i}", year=2000 + i, tmdb=str(100 + i))
    allow(two, user_id=2, username="bob", cap=2)
    assert post(two, "k-bob", title="M0", year=2000, tmdb_id=100).status_code == 200
    r = two.post("/api/knm/download", json={"kind": "movie", "title": "M1", "year": 2001, "tmdb_id": 101},
                 headers=H("k-bob2", two.server2))
    assert r.status_code == 200
    assert post(two, "k-bob", title="M2", year=2002, tmdb_id=102).status_code == 429
    assert me(two, "k-bob2", two.server2)["used_today"] == 2


def test_migration_adds_username_indexes_and_keeps_rows(db):
    store.upsert_entry(1, 5, "Old", True, None)
    store.ensure_schema()
    names = {r["name"] for r in store.rows("SELECT name FROM sqlite_master WHERE type='index'")}
    assert {"idx_knm_allowlist_username", "idx_knm_requests_username"} <= names
    assert store.get_entry(1, 5)["username"] == "Old"
