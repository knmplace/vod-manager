# KNM: 2026-11-05 - posters on a dead image host, or missing, are filled from our own
# TMDB store first (no API call), then TMDB, then MDBList; a saved TMDB poster is never
# replaced by a provider poster on a later import or enrichment.
import asyncio

import pytest

import config
import mdblist_artwork
import poster_repair as pr
import tmdb_store
import tmdb_sync

LOCAL = "https://image.tmdb.org/t/p/w500/local.jpg"
API = "https://image.tmdb.org/t/p/w500/api.jpg"
MDB = "https://mdblist.example/poster.jpg"


def _store(media_type, tmdb_id, poster_path):
    tmdb_store.init_db()
    tmdb_store.upsert_payload(media_type, {"id": tmdb_id, "title": "X", "name": "X", "poster_path": poster_path})


@pytest.fixture()
def remote(monkeypatch):
    calls = {"tmdb": [], "mdb": []}

    async def tmdb(tmdb_id):
        calls["tmdb"].append(tmdb_id)
        return {"poster_url": API}

    async def mdb_lookup(kind, tmdb_id, title, year):
        calls["mdb"].append(tmdb_id)
        return [{"poster_url": MDB, "tmdb_id_match": True, "identity_match": False}]

    async def mdb_search(kind, title, year):
        calls["mdb"].append(title)
        return [{"poster_url": MDB, "identity_match": True}]

    monkeypatch.setattr(tmdb_sync, "get_movie_full_details", tmdb)
    monkeypatch.setattr(tmdb_sync, "get_series_full_details", tmdb)
    monkeypatch.setattr(mdblist_artwork, "lookup_by_tmdb_id", mdb_lookup)
    monkeypatch.setattr(mdblist_artwork, "search_by_title", mdb_search)
    monkeypatch.setattr(config, "get_mdblist_artwork_settings", lambda: {"enabled": True, "account_tier": "free"})
    monkeypatch.setattr(config, "get_mdblist_api_key", lambda: "k")
    return calls


def test_local_store_poster_is_used_without_any_api_call(db, remote):
    _store("movie", 550, "/local.jpg")
    assert asyncio.run(pr.resolve_poster("movie", {"tmdb_id": "550", "name": "X"})) == LOCAL
    assert remote == {"tmdb": [], "mdb": []}


def test_series_reads_tv_rows_from_local_store(db, remote):
    _store("tv", 77, "/local.jpg")
    assert asyncio.run(pr.resolve_poster("series", {"tmdb_id": "77", "name": "X"})) == LOCAL


def test_falls_back_to_tmdb_then_mdblist(db, remote, monkeypatch):
    assert asyncio.run(pr.resolve_poster("movie", {"tmdb_id": "9", "name": "X"})) == API

    async def none(tmdb_id):
        return {"poster_url": None}
    monkeypatch.setattr(tmdb_sync, "get_movie_full_details", none)
    assert asyncio.run(pr.resolve_poster("movie", {"tmdb_id": "9", "name": "X"})) == MDB
    assert remote["mdb"] == ["9"]


def test_no_tmdb_id_uses_mdblist_title_search_only_on_identity_match(db, remote, monkeypatch):
    assert asyncio.run(pr.resolve_poster("movie", {"tmdb_id": None, "name": "Film", "year": 2001})) == MDB
    assert remote["tmdb"] == []

    async def loose(kind, title, year):
        return [{"poster_url": MDB, "identity_match": False}]
    monkeypatch.setattr(mdblist_artwork, "search_by_title", loose)
    assert asyncio.run(pr.resolve_poster("movie", {"tmdb_id": None, "name": "Film"})) is None


def test_mdblist_skipped_when_disabled(db, remote, monkeypatch):
    monkeypatch.setattr(config, "get_mdblist_artwork_settings", lambda: {"enabled": False, "account_tier": "free"})
    assert asyncio.run(pr.resolve_poster("movie", {"tmdb_id": None, "name": "Film"})) is None
    assert remote["mdb"] == []


def test_mdblist_quota_reached_is_not_an_error(db, remote, monkeypatch):
    async def limited(*a):
        raise ValueError("MDBList artwork search daily limit reached")
    monkeypatch.setattr(mdblist_artwork, "search_by_title", limited)
    assert asyncio.run(pr.resolve_poster("movie", {"tmdb_id": None, "name": "Film"})) is None


def _movie(db, name, poster, tmdb_id=None):
    mid = db.upsert_movie(name, 2020)
    conn = db._connect()
    conn.execute("UPDATE movies SET poster_url=?, tmdb_id=? WHERE id=?", (poster, tmdb_id, mid))
    conn.commit()
    conn.close()
    return mid


def _poster(db, table, item_id):
    conn = db._connect()
    try:
        return conn.execute(f"SELECT poster_url FROM {table} WHERE id=?", (item_id,)).fetchone()[0]
    finally:
        conn.close()


def test_repair_swaps_dead_host_and_fills_missing_but_leaves_live_hosts(db, remote):
    _store("movie", 1, "/local.jpg")
    dead = [_movie(db, f"dead{i}", f"http://dead.invalid/{i}.jpg", str(i)) for i in (1, 2)]
    live = _movie(db, "live", "http://live.example/a.jpg", "3")
    empty = _movie(db, "empty", None, "4")
    bare = _movie(db, "bare", "https://image.tmdb.org/t/p/w600_and_h900_bestv2", "5")

    async def probe(url):
        return "live.example" in url
    out = asyncio.run(pr.repair_posters(probe=probe))
    assert _poster(db, "movies", dead[0]) == LOCAL
    assert _poster(db, "movies", dead[1]) == API
    assert _poster(db, "movies", live) == "http://live.example/a.jpg"
    assert _poster(db, "movies", empty) == API and _poster(db, "movies", bare) == API
    assert out["dead_hosts"] == ["dead.invalid"]
    assert out["movies_fixed"] == 4


def test_repair_never_probes_or_swaps_tmdb_hosted_posters(db, remote):
    tmdb_poster = "https://image.tmdb.org/t/p/w500/keep.jpg"
    mid = _movie(db, "kept", tmdb_poster, "8")
    probed = []

    async def probe(url):
        probed.append(url)
        return False
    asyncio.run(pr.repair_posters(probe=probe))
    assert probed == [] and _poster(db, "movies", mid) == tmdb_poster


def test_saved_tmdb_poster_survives_provider_enrichment(db):
    tmdb_poster = "https://image.tmdb.org/t/p/w500/keep.jpg"
    sid = db.upsert_series("Show", None)
    conn = db._connect()
    conn.execute("UPDATE series SET poster_url=? WHERE id=?", (tmdb_poster, sid))
    conn.commit()
    conn.close()
    db.set_series_enrichment(sid, poster_url="http://provider.example/cover.jpg")
    assert _poster(db, "series", sid) == tmdb_poster
    db.set_series_enrichment(sid, poster_url="https://image.tmdb.org/t/p/w500/newer.jpg")
    assert _poster(db, "series", sid) == "https://image.tmdb.org/t/p/w500/newer.jpg"


def test_enrichment_without_poster_does_not_blank_existing(db):
    mid = _movie(db, "m", "http://provider.example/a.jpg")
    db.set_movie_enrichment(mid, poster_url=None)
    assert _poster(db, "movies", mid) == "http://provider.example/a.jpg"
    db.apply_movie_enrichment_batch([{"movie_id": mid, "fields": {"poster_url": None}}])
    assert _poster(db, "movies", mid) == "http://provider.example/a.jpg"


def test_saved_tmdb_movie_poster_survives_batch_provider_poster(db):
    tmdb_poster = "https://image.tmdb.org/t/p/w500/keep.jpg"
    mid = _movie(db, "m2", tmdb_poster)
    db.apply_movie_enrichment_batch([{"movie_id": mid, "fields": {"poster_url": "http://p.example/x.jpg"}}])
    assert _poster(db, "movies", mid) == tmdb_poster
