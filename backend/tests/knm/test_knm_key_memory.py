# KNM FORK ONLY - NEVER SEND UPSTREAM
"""Which stored connection a key belongs to is remembered, and rejected keys are not re-sent.

Dispatcharr rate-limits failed API key attempts per client IP, so every needless wrong-server
attempt counts against all users behind vod_manager. DispatcharrClient.get is faked (not
fetch_me) so the real status-code handling runs."""

import hashlib

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import vod_db
from knm import auth as knm_auth
from knm import routes as knm_routes

A = "http://disp.example:9191"
B = "http://other.example:9191"
BOB = {"id": 2, "username": "bob", "user_level": 1}


class World:
    """Fake Dispatcharr servers: accounts[url][key] -> user, failures[url] -> status or exception."""

    def __init__(self):
        self.accounts = {A: {}, B: {"k-bob": BOB}}
        self.failures = {}
        self.seen = []
        self.now = 1_000_000.0

    def sent(self):
        out, self.seen = self.seen, []
        return out


@pytest.fixture()
def world(db, monkeypatch):
    w = World()

    async def fake_get(self, path, params=None):
        url, key = self._base, self._headers["X-API-Key"]
        w.seen.append((url, key))
        failure = w.failures.get(url)
        if isinstance(failure, Exception):
            raise failure
        user = w.accounts.get(url, {}).get(key)
        status = failure or (200 if user else 401)
        if status != 200:
            request = httpx.Request("GET", url + path)
            raise httpx.HTTPStatusError("nope", request=request,
                                        response=httpx.Response(status, request=request))
        return dict(user)

    monkeypatch.setattr(knm_auth.DispatcharrClient, "get", fake_get)
    monkeypatch.setattr(knm_auth.time, "time", lambda: w.now)
    w.a = vod_db.create_dispatcharr_connection("Newton", A, "STORED")
    w.b = vod_db.create_dispatcharr_connection("Other", B, "S2")
    knm_auth.clear_cache()
    app = FastAPI()
    app.include_router(knm_routes.router)
    w.client = TestClient(app)
    yield w
    knm_auth.clear_cache()


def me(w, key="k-bob", server=None):
    headers = {"X-Dispatcharr-Key": key}
    if server is not None:
        headers["X-Dispatcharr-Server"] = str(server)
    return w.client.get("/api/knm/me", headers=headers)


def past_identity_cache(w):
    w.now += knm_auth.CACHE_SECONDS + 1


def past_rejection(w):
    w.now += knm_auth.REJECT_SECONDS + 1


# -- remembered connection ----------------------------------------------------

def test_accepting_connection_is_tried_first_after_identity_cache_expires(world):
    assert me(world).json()["server_id"] == world.b
    assert world.sent() == [(A, "k-bob"), (B, "k-bob")]
    past_identity_cache(world)
    assert me(world).json()["server_id"] == world.b
    assert world.sent() == [(B, "k-bob")]


def test_remembered_connection_still_first_after_rejection_ttl(world):
    me(world)
    world.sent()
    past_rejection(world)
    assert me(world).status_code == 200
    assert world.sent() == [(B, "k-bob")]


def test_remembered_connection_rejecting_is_forgotten_and_others_tried(world):
    me(world)
    past_rejection(world)
    world.sent()
    world.accounts = {A: {"k-bob": BOB}, B: {}}
    assert me(world).json()["server_id"] == world.a
    assert world.sent() == [(B, "k-bob"), (A, "k-bob")]
    past_rejection(world)
    assert me(world).status_code == 200
    assert world.sent() == [(A, "k-bob")]


def test_remembered_connection_rejecting_everywhere_is_dropped(world):
    me(world)
    past_rejection(world)
    world.accounts = {A: {}, B: {}}
    assert me(world).status_code == 401
    assert knm_auth._remembered == {}


def test_raw_key_is_never_stored(world):
    me(world)
    stored = repr((knm_auth._remembered, knm_auth._rejected, knm_auth._cache))
    assert "k-bob" not in stored
    assert hashlib.sha256(b"k-bob").hexdigest() in knm_auth._remembered


def test_remembered_connection_unreachable_is_kept(world):
    me(world)
    past_identity_cache(world)
    world.failures[B] = httpx.ConnectError("down")
    assert me(world).status_code == 502
    del world.failures[B]
    past_rejection(world)
    world.sent()
    assert me(world).status_code == 200
    assert world.sent() == [(B, "k-bob")]


def test_deleted_remembered_connection_gets_nothing(world):
    me(world)
    past_rejection(world)
    world.sent()
    vod_db.delete_dispatcharr_connection(world.b)
    assert me(world).status_code == 401
    assert world.sent() == [(A, "k-bob")]


# -- rejected keys ------------------------------------------------------------

@pytest.mark.parametrize("status", [401, 403])
def test_rejected_key_not_resent_until_ttl(world, status):
    world.failures = {A: status, B: status}
    assert me(world).status_code == 401
    assert world.sent() == [(A, "k-bob"), (B, "k-bob")]
    world.now += knm_auth.REJECT_SECONDS - 5
    r = me(world)
    assert r.status_code == 401 and r.json()["detail"] == "Invalid key"
    assert world.sent() == []
    world.now += 10
    me(world)
    assert world.sent() == [(A, "k-bob"), (B, "k-bob")]


def test_rejected_key_not_resent_with_server_header(world):
    for _ in range(3):
        r = me(world, server=world.a)
        assert r.status_code == 401 and r.json()["detail"] == "Invalid key"
    assert world.sent() == [(A, "k-bob")]


def test_rejection_is_shared_between_header_and_no_header(world):
    me(world, server=world.a)
    world.sent()
    assert me(world).status_code == 200
    assert world.sent() == [(B, "k-bob")]


def test_rejection_is_per_connection_and_per_key(world):
    me(world, server=world.a)
    world.sent()
    assert me(world, server=world.b).status_code == 200
    me(world, key="k-other", server=world.a)
    assert world.sent() == [(B, "k-bob"), (A, "k-other")]


@pytest.mark.parametrize("failure", [429, 500, 503, httpx.ConnectError("down"),
                                     httpx.ReadTimeout("slow")])
def test_temporary_failures_are_never_negative_cached(world, failure):
    world.failures = {A: failure, B: failure}
    for _ in range(2):
        assert me(world).status_code == 502
        assert world.sent() == [(A, "k-bob"), (B, "k-bob")]
    assert knm_auth._rejected == {}


def test_unreachable_plus_cached_rejection_stays_502(world):
    world.failures = {B: 503}
    assert me(world).status_code == 502
    world.sent()
    assert me(world).status_code == 502
    assert world.sent() == [(B, "k-bob")]


def test_odd_success_body_is_not_negative_cached(world):
    world.accounts = {A: {"k-bob": {"detail": "no id here"}}, B: {}}
    for _ in range(2):
        assert me(world, server=world.a).status_code == 401
    assert world.sent() == [(A, "k-bob"), (A, "k-bob")]


def test_changed_connection_url_drops_old_rejection(world):
    assert me(world, server=world.a).status_code == 401
    world.sent()
    moved = "http://moved.example:9191"
    world.accounts[moved] = {"k-bob": BOB}
    vod_db.update_dispatcharr_connection(world.a, url=moved)
    assert me(world, server=world.a).status_code == 200
    assert world.sent() == [(moved, "k-bob")]


# -- bounds and clearing ------------------------------------------------------

def test_both_maps_are_bounded(world, monkeypatch):
    monkeypatch.setattr(knm_auth, "MAX_ENTRIES", 5)
    for i in range(20):
        world.accounts[B][f"good-{i}"] = BOB
        me(world, key=f"good-{i}")
        me(world, key=f"bad-{i}")
    assert len(knm_auth._remembered) == 5 and len(knm_auth._rejected) == 5


def test_recently_used_key_survives_eviction(world, monkeypatch):
    monkeypatch.setattr(knm_auth, "MAX_ENTRIES", 2)
    for key in ("k1", "k2", "k3"):
        world.accounts[B][key] = BOB
    me(world, key="k1")
    me(world, key="k2")
    past_identity_cache(world)
    me(world, key="k1")
    me(world, key="k3")
    assert set(knm_auth._remembered) == {hashlib.sha256(k).hexdigest() for k in (b"k1", b"k3")}


def test_clear_cache_clears_everything(world):
    me(world)
    assert knm_auth._cache and knm_auth._remembered and knm_auth._rejected
    knm_auth.clear_cache()
    assert not (knm_auth._cache or knm_auth._remembered or knm_auth._rejected)
    world.sent()
    me(world)
    assert world.sent() == [(A, "k-bob"), (B, "k-bob")]
