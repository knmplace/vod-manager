# KNM FORK ONLY - NEVER SEND UPSTREAM
"""Admin-session routes (/api/knm/admin/*): guarded by the vod_manager admin login, not a Dispatcharr key."""

import pytest

import notices
import routes as core_routes
import vod_db
from test_knm_api import H, _jobs, _movie, _set_job, allow, client, post  # noqa: F401  (client is a fixture)

A = {"X-Session-Token": "good"}


@pytest.fixture()
def secured(client, monkeypatch):
    monkeypatch.setattr(core_routes, "has_credentials", lambda: True)
    monkeypatch.setattr(core_routes, "verify_session", lambda t: t == "good")
    return client


def _failed_request(client, db):
    _movie(db)
    allow(client)
    post(client, title="Some Movie", year=2001, tmdb_id=777)
    _set_job(status="failed", error="HTTP 503 from provider")
    client.get("/api/knm/downloads", headers=H("k-bob", client.server_id))   # syncs + raises the notice


def test_admin_routes_need_session(secured):
    for method, path in [("get", "/api/knm/admin/allowlist"), ("get", "/api/knm/admin/requests"),
                         ("get", "/api/knm/admin/notices")]:
        assert getattr(secured, method)(path).status_code == 401
        assert getattr(secured, method)(path, headers={"X-Session-Token": "bad"}).status_code == 401


def test_dispatcharr_key_does_not_open_admin_routes(secured):
    r = secured.get("/api/knm/admin/allowlist", headers=H("k-admin", secured.server_id))
    assert r.status_code == 401


def test_allowlist_roundtrip_and_default_cap(secured):
    r = secured.put("/api/knm/admin/allowlist", headers=A, json={
        "default_cap": 8, "entries": [{"server_id": secured.server_id, "user_id": 2, "username": "bob",
                                       "allowed": True, "daily_cap": 3}]})
    assert r.status_code == 200
    got = secured.get("/api/knm/admin/allowlist", headers=A).json()
    assert got["default_cap"] == 8
    assert [(e["user_id"], e["username"], e["daily_cap"], e["allowed"]) for e in got["entries"]] == [(2, "bob", 3, True)]
    me = secured.get("/api/knm/me", headers=H("k-bob", secured.server_id)).json()
    assert me["allowed"] is True and me["cap"] == 3


def test_allowlist_remove_entry(secured):
    secured.put("/api/knm/admin/allowlist", headers=A, json={"entries": [
        {"server_id": secured.server_id, "user_id": 2, "username": "bob", "allowed": True}]})
    assert secured.delete(f"/api/knm/admin/allowlist/{secured.server_id}/2", headers=A).status_code == 200
    assert secured.get("/api/knm/admin/allowlist", headers=A).json()["entries"] == []
    assert secured.delete(f"/api/knm/admin/allowlist/{secured.server_id}/2", headers=A).status_code == 404
    assert secured.get("/api/knm/me", headers=H("k-bob", secured.server_id)).json()["allowed"] is False


def test_allowlist_bad_cap_422(secured):
    assert secured.put("/api/knm/admin/allowlist", headers=A, json={"default_cap": -1}).status_code == 422


def test_requests_lists_everyones_with_detail_and_filter(secured, db):
    _movie(db, name="A", year=2001, tmdb="1")
    _movie(db, name="B", year=2002, tmdb="2")
    allow(secured)
    allow(secured, user_id=3, username="amy")
    post(secured, title="A", year=2001, tmdb_id=1)
    post(secured, key="k-amy", title="B", year=2002, tmdb_id=2)
    vod_db.update_download_job(_jobs()[0]["id"], status="failed", error="boom 503")
    out = secured.get("/api/knm/admin/requests", headers=A).json()
    assert {r["title"] for r in out["requests"]} == {"A", "B"}
    assert out["counts"]["failed"] == 1 and out["counts"]["queued"] == 1
    bad = next(r for r in out["requests"] if r["status"] == "failed")
    assert bad["username"] == "bob" and "503" in bad["detail"]
    only = secured.get("/api/knm/admin/requests?status=failed", headers=A).json()["requests"]
    assert [r["title"] for r in only] == ["A"]


def test_retry_requeues_failed_jobs_and_allows_new_notice(secured, db):
    _failed_request(secured, db)
    rid = secured.get("/api/knm/admin/requests", headers=A).json()["requests"][0]["id"]
    r = secured.post(f"/api/knm/admin/requests/{rid}/retry", headers=A)
    assert r.status_code == 200 and r.json()["status"] == "queued"
    assert _jobs()[0]["status"] == "queued"
    _set_job(status="failed", error="again")
    secured.get("/api/knm/downloads", headers=H("k-bob", secured.server_id))
    assert len(secured.get("/api/knm/admin/notices", headers=A).json()["notices"]) == 1


def test_retry_nothing_retryable_409(secured, db):
    _movie(db)
    allow(secured)
    post(secured, title="Some Movie", year=2001, tmdb_id=777)
    rid = secured.get("/api/knm/admin/requests", headers=A).json()["requests"][0]["id"]
    assert secured.post(f"/api/knm/admin/requests/{rid}/retry", headers=A).status_code == 409


def test_cancel_stops_jobs_and_marks_cancelled(secured, db):
    _movie(db)
    allow(secured)
    post(secured, title="Some Movie", year=2001, tmdb_id=777)
    rid = secured.get("/api/knm/admin/requests", headers=A).json()["requests"][0]["id"]
    r = secured.post(f"/api/knm/admin/requests/{rid}/cancel", headers=A)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert _jobs()[0]["status"] == "cancelled"
    # a cancelled request no longer blocks asking for the title again
    assert post(secured, title="Some Movie", year=2001, tmdb_id=777).status_code == 200


def test_unknown_request_404(secured):
    assert secured.post("/api/knm/admin/requests/999/retry", headers=A).status_code == 404
    assert secured.post("/api/knm/admin/requests/999/cancel", headers=A).status_code == 404


def test_failed_notices_listed_and_cleared(secured, db):
    _failed_request(secured, db)
    n = secured.get("/api/knm/admin/notices", headers=A).json()["notices"]
    assert len(n) == 1 and n[0]["title"] == "Some Movie" and n[0]["username"] == "bob"
    assert "503" in n[0]["detail"]
    assert secured.post("/api/knm/admin/notices/clear", headers=A).json()["cleared"] == 1
    assert secured.get("/api/knm/admin/notices", headers=A).json()["notices"] == []
    assert notices.list_open() == []                       # the vod_manager bell notice is acknowledged too
    # still visible to the person who asked
    assert len(secured.get("/api/knm/notices", headers=H("k-bob", secured.server_id)).json()["notices"]) == 1


def test_mount_unchanged_single_line():
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[2] / "main.py").read_text(encoding="utf-8")
    assert src.count("KNM-ONLY:") == 1
