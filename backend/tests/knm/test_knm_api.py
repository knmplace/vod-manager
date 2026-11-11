# KNM FORK ONLY - NEVER SEND UPSTREAM
"""/api/knm/* endpoints: auth, allow-list, cap, matching, enqueue, statuses, notices."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import config
import notices
import vod_db
from knm import auth as knm_auth
from knm import routes as knm_routes
from knm import store

from test_arr_handoff import _jobs, _series, _set_tmdb

_stream = iter(range(1000, 100000))


def _movie(db, name="Some Movie", year=2001, tmdb="777"):
    """Like test_arr_handoff._movie but with a unique stream id so several movies can coexist."""
    pid = db.upsert_provider("p1", "http://prov", "u", "pw")
    mid = db.upsert_movie(name, year)
    if tmdb:
        _set_tmdb(db, "movies", mid, tmdb)
    db.add_movie_source(mid, pid, str(next(_stream)), "mp4")
    return mid

KEYS = {
    "k-admin": {"id": 1, "username": "boss", "user_level": 10},
    "k-bob": {"id": 2, "username": "bob", "user_level": 1},
    "k-amy": {"id": 3, "username": "amy", "user_level": 1},
}


@pytest.fixture()
def client(db, tmp_path, monkeypatch):
    config.save_download_settings({"enabled": True, "output_dir": str(tmp_path / "lib"), "min_free_gb": 0})
    conn_id = vod_db.create_dispatcharr_connection("Newton", "http://disp.example:9191", "STORED")
    seen = []

    async def fake_me(connection, key):
        seen.append((connection["url"], key))
        if key not in KEYS:
            raise knm_auth.InvalidKey()
        return dict(KEYS[key])

    monkeypatch.setattr(knm_auth, "fetch_me", fake_me)
    knm_auth.clear_cache()
    app = FastAPI()
    app.include_router(knm_routes.router)
    c = TestClient(app)
    c.server_id = conn_id
    c.seen = seen
    return c


def H(key, server):
    return {"X-Dispatcharr-Key": key, "X-Dispatcharr-Server": str(server)}


def allow(c, user_id=2, username="bob", cap=None, who="k-admin"):
    body = {"entries": [{"server_id": c.server_id, "user_id": user_id, "username": username,
                         "allowed": True, "daily_cap": cap}]}
    r = c.put("/api/knm/allowlist", json=body, headers=H(who, c.server_id))
    assert r.status_code == 200, r.text


# -- auth ---------------------------------------------------------------------

def test_missing_headers_401(client):
    assert client.get("/api/knm/me").status_code == 401


def test_bad_key_401(client):
    assert client.get("/api/knm/me", headers=H("nope", client.server_id)).status_code == 401


def test_unknown_server_401_and_no_outbound_call(client):
    r = client.get("/api/knm/me", headers=H("k-bob", 9999))
    assert r.status_code == 401 and client.seen == []


def test_non_integer_server_rejected(client):
    r = client.get("/api/knm/me", headers={"X-Dispatcharr-Key": "k-bob", "X-Dispatcharr-Server": "http://evil"})
    assert r.status_code == 401 and client.seen == []


def test_validates_against_stored_url_only(client):
    client.get("/api/knm/me", headers=H("k-bob", client.server_id))
    assert client.seen == [("http://disp.example:9191", "k-bob")]


def test_key_validation_cached(client):
    for _ in range(3):
        client.get("/api/knm/me", headers=H("k-bob", client.server_id))
    assert len(client.seen) == 1


def test_upstream_unreachable_is_502(client, monkeypatch):
    async def boom(connection, key):
        raise RuntimeError("down")
    monkeypatch.setattr(knm_auth, "fetch_me", boom)
    assert client.get("/api/knm/me", headers=H("k-bob", client.server_id)).status_code == 502


# -- me / allow-list / cap ----------------------------------------------------

def test_me_default_not_allowed(client):
    r = client.get("/api/knm/me", headers=H("k-bob", client.server_id)).json()
    assert r["allowed"] is False and r["is_admin"] is False and r["cap"] == 5 and r["used_today"] == 0


def test_me_admin_allowed(client):
    r = client.get("/api/knm/me", headers=H("k-admin", client.server_id)).json()
    assert r["is_admin"] is True and r["allowed"] is True


def test_allowlist_admin_only(client):
    assert client.get("/api/knm/allowlist", headers=H("k-bob", client.server_id)).status_code == 403
    r = client.put("/api/knm/allowlist", json={"entries": []}, headers=H("k-bob", client.server_id))
    assert r.status_code == 403


def test_allowlist_roundtrip_and_cap(client):
    allow(client, cap=2)
    got = client.get("/api/knm/allowlist", headers=H("k-admin", client.server_id)).json()
    assert got["default_cap"] == 5
    assert got["entries"][0]["user_id"] == 2 and got["entries"][0]["daily_cap"] == 2
    me = client.get("/api/knm/me", headers=H("k-bob", client.server_id)).json()
    assert me["allowed"] is True and me["cap"] == 2


def test_default_cap_adjustable(client):
    r = client.put("/api/knm/allowlist", json={"default_cap": 9, "entries": []},
                   headers=H("k-admin", client.server_id))
    assert r.status_code == 200
    assert client.get("/api/knm/allowlist", headers=H("k-admin", client.server_id)).json()["default_cap"] == 9


def test_bad_cap_rejected(client):
    r = client.put("/api/knm/allowlist", json={"default_cap": -1, "entries": []},
                   headers=H("k-admin", client.server_id))
    assert r.status_code in (400, 422)


def test_allowlist_can_disallow(client):
    allow(client)
    client.put("/api/knm/allowlist", json={"entries": [
        {"server_id": client.server_id, "user_id": 2, "allowed": False}]}, headers=H("k-admin", client.server_id))
    assert client.get("/api/knm/me", headers=H("k-bob", client.server_id)).json()["allowed"] is False


# -- download -----------------------------------------------------------------

def post(c, key="k-bob", **body):
    body.setdefault("kind", "movie")
    return c.post("/api/knm/download", json=body, headers=H(key, c.server_id))


def test_download_not_allowed_403(client, db):
    _movie(db)
    assert post(client, title="Some Movie", year=2001, tmdb_id=777).status_code == 403
    assert _jobs() == []


def test_download_matches_by_tmdb_and_enqueues(client, db):
    mid = _movie(db, name="Some Movie", year=2001, tmdb="777")
    allow(client)
    r = post(client, title="Totally Different Title", year=1999, tmdb_id=777)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "queued" and body["id"]
    jobs = _jobs()
    assert len(jobs) == 1 and jobs[0]["item_id"] == mid and jobs[0]["kind"] == "movie"


def test_download_falls_back_to_title_year(client, db):
    _movie(db, name="Some Movie", year=2001, tmdb=None)
    allow(client)
    assert post(client, title="some movie", year=2001).status_code == 200
    assert len(_jobs()) == 1


def test_title_fallback_requires_year_match(client, db):
    _movie(db, name="Some Movie", year=2001, tmdb=None)
    allow(client)
    assert post(client, title="Some Movie", year=1990).status_code == 404
    assert _jobs() == []


def test_no_match_404(client, db):
    allow(client)
    assert post(client, title="Nope", year=2020, tmdb_id=1).status_code == 404


def test_show_enqueues_all_episodes(client, db):
    _series(db, episodes=((1, 1), (1, 2), (2, 1)), tmdb="555")
    allow(client)
    r = post(client, kind="show", title="Show", year=2020, tmdb_id=555)
    assert r.status_code == 200, r.text
    assert len(_jobs()) == 3 and r.json()["episodes_total"] == 3


def test_bad_kind_422(client, db):
    allow(client)
    assert post(client, kind="album", title="x", year=2000).status_code == 422


def test_daily_cap_enforced(client, db):
    for i in range(3):
        _movie(db, name=f"M{i}", year=2000 + i, tmdb=str(100 + i))
    allow(client, cap=2)
    assert post(client, title="M0", year=2000, tmdb_id=100).status_code == 200
    assert post(client, title="M1", year=2001, tmdb_id=101).status_code == 200
    assert post(client, title="M2", year=2002, tmdb_id=102).status_code == 429
    me = client.get("/api/knm/me", headers=H("k-bob", client.server_id)).json()
    assert me["used_today"] == 2 and me["cap"] == 2


def test_default_cap_five(client, db):
    for i in range(6):
        _movie(db, name=f"M{i}", year=2000 + i, tmdb=str(100 + i))
    allow(client)
    codes = [post(client, title=f"M{i}", year=2000 + i, tmdb_id=100 + i).status_code for i in range(6)]
    assert codes == [200] * 5 + [429]


def test_duplicate_request_returns_same_and_costs_nothing(client, db):
    _movie(db)
    allow(client)
    a = post(client, title="Some Movie", year=2001, tmdb_id=777).json()
    b = post(client, title="Some Movie", year=2001, tmdb_id=777).json()
    assert a["id"] == b["id"] and len(_jobs()) == 1
    assert client.get("/api/knm/me", headers=H("k-bob", client.server_id)).json()["used_today"] == 1


def test_already_in_library_is_ready_without_download(client, db):
    mid = _movie(db)
    conn = db._connect()
    conn.execute("INSERT INTO library_presence_items (kind, item_id, label) VALUES ('movie', ?, 'Plex: Movies')", (mid,))
    conn.commit()
    conn.close()
    allow(client)
    r = post(client, title="Some Movie", year=2001, tmdb_id=777).json()
    assert r["status"] == "ready" and _jobs() == []


# -- listing, scoping, status progression -------------------------------------

def test_downloads_scoped_to_user_and_admin_all(client, db):
    _movie(db, name="A", year=2001, tmdb="1")
    _movie(db, name="B", year=2002, tmdb="2")
    allow(client, 2, "bob")
    allow(client, 3, "amy")
    post(client, "k-bob", title="A", year=2001, tmdb_id=1)
    post(client, "k-amy", title="B", year=2002, tmdb_id=2)
    mine = client.get("/api/knm/downloads", headers=H("k-bob", client.server_id)).json()
    assert [d["title"] for d in mine["downloads"]] == ["A"]
    everyone = client.get("/api/knm/downloads?all=1", headers=H("k-admin", client.server_id)).json()
    assert {d["title"] for d in everyone["downloads"]} == {"A", "B"}
    still = client.get("/api/knm/downloads?all=1", headers=H("k-bob", client.server_id)).json()
    assert [d["title"] for d in still["downloads"]] == ["A"]      # not an escalation


def test_downloads_newest_first(client, db):
    _movie(db, name="A", year=2001, tmdb="1")
    _movie(db, name="B", year=2002, tmdb="2")
    allow(client)
    post(client, title="A", year=2001, tmdb_id=1)
    post(client, title="B", year=2002, tmdb_id=2)
    d = client.get("/api/knm/downloads", headers=H("k-bob", client.server_id)).json()["downloads"]
    assert [x["title"] for x in d] == ["B", "A"]


def _set_job(**fields):
    vod_db.update_download_job(_jobs()[0]["id"], **fields)


def test_status_follows_job_and_ready_raises_user_notice(client, db):
    _movie(db)
    allow(client)
    post(client, title="Some Movie", year=2001, tmdb_id=777)
    hdr = H("k-bob", client.server_id)
    _set_job(status="running", progress=0.3)
    assert client.get("/api/knm/downloads", headers=hdr).json()["downloads"][0]["status"] == "downloading"
    _set_job(status="done", import_status="waiting")
    assert client.get("/api/knm/downloads", headers=hdr).json()["downloads"][0]["status"] == "processing"
    _set_job(import_status="imported")
    d = client.get("/api/knm/downloads", headers=hdr).json()["downloads"][0]
    assert d["status"] == "ready" and d["label"]
    n = client.get("/api/knm/notices", headers=hdr).json()["notices"]
    assert len(n) == 1 and n[0]["kind"] == "ready" and n[0]["title"] == "Some Movie" and n[0]["tmdb_id"] == "777"
    client.get("/api/knm/downloads", headers=hdr)                 # not duplicated on the next poll
    assert len(client.get("/api/knm/notices", headers=hdr).json()["notices"]) == 1


def test_notice_ack(client, db):
    _movie(db)
    allow(client)
    post(client, title="Some Movie", year=2001, tmdb_id=777)
    _set_job(status="done", import_status="imported")
    hdr = H("k-bob", client.server_id)
    client.get("/api/knm/downloads", headers=hdr)
    nid = client.get("/api/knm/notices", headers=hdr).json()["notices"][0]["id"]
    assert client.post("/api/knm/notices/ack", json={"ids": [nid]}, headers=hdr).status_code == 200
    assert client.get("/api/knm/notices", headers=hdr).json()["notices"] == []


def test_notice_ack_cannot_touch_other_users(client, db):
    _movie(db)
    allow(client)
    post(client, title="Some Movie", year=2001, tmdb_id=777)
    _set_job(status="done", import_status="imported")
    client.get("/api/knm/downloads", headers=H("k-bob", client.server_id))
    nid = client.get("/api/knm/notices", headers=H("k-bob", client.server_id)).json()["notices"][0]["id"]
    client.post("/api/knm/notices/ack", json={"ids": [nid]}, headers=H("k-amy", client.server_id))
    assert len(client.get("/api/knm/notices", headers=H("k-bob", client.server_id)).json()["notices"]) == 1


def test_failure_raises_admin_notice_and_log(client, db, caplog):
    _movie(db)
    allow(client)
    post(client, title="Some Movie", year=2001, tmdb_id=777)
    _set_job(status="failed", error="HTTP 503 from provider")
    hdr = H("k-bob", client.server_id)
    with caplog.at_level("WARNING"):
        d = client.get("/api/knm/downloads", headers=hdr).json()["downloads"][0]
    assert d["status"] == "failed"
    assert "503" not in str(d)                      # no technical detail to the person
    open_ = notices.list_open()
    assert len(open_) == 1 and open_[0]["kind"] == "knm_download" and "503" in open_[0]["body"]
    assert any("503" in r.getMessage() for r in caplog.records)
    client.get("/api/knm/downloads", headers=hdr)   # one notice only, however often it is polled
    assert len(notices.list_open()) == 1
    n = client.get("/api/knm/notices", headers=hdr).json()["notices"]
    assert n[0]["kind"] == "failed" and "503" not in str(n)


def test_needs_manual_raises_admin_notice(client, db):
    _movie(db)
    allow(client)
    post(client, title="Some Movie", year=2001, tmdb_id=777)
    _set_job(status="done", import_status="needs_manual", import_note="Add this title to Radarr/Sonarr manually")
    client.get("/api/knm/downloads", headers=H("k-bob", client.server_id))
    assert [n["kind"] for n in notices.list_open()] == ["knm_download"]


def test_admin_downloads_include_detail_user_does_not(client, db):
    _movie(db)
    allow(client)
    post(client, title="Some Movie", year=2001, tmdb_id=777)
    _set_job(status="failed", error="HTTP 503 from provider")
    adm = client.get("/api/knm/downloads?all=1", headers=H("k-admin", client.server_id)).json()["downloads"][0]
    assert "503" in adm["detail"] and adm["username"] == "bob"
    usr = client.get("/api/knm/downloads", headers=H("k-bob", client.server_id)).json()["downloads"][0]
    assert "detail" not in usr


def test_admin_notices_include_others_failures(client, db):
    _movie(db)
    allow(client)
    post(client, title="Some Movie", year=2001, tmdb_id=777)
    _set_job(status="failed", error="x")
    client.get("/api/knm/downloads", headers=H("k-bob", client.server_id))
    adm = client.get("/api/knm/notices", headers=H("k-admin", client.server_id)).json()["notices"]
    assert any(n["kind"] == "failed" and n["username"] == "bob" for n in adm)


def test_tables_created_by_knm(db):
    store.ensure_schema()
    conn = db._connect()
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert {"knm_requests", "knm_allowlist", "knm_settings", "knm_notices"} <= names


def test_mount_line_present_and_marked():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[2] / "main.py").read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if "KNM-ONLY:" in ln]
    assert len(lines) == 1 and "knm" in lines[0]
