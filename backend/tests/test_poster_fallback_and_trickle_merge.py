"""A card whose stored poster fails to load swaps to the TMDB poster, and the
episode trickle only re-runs merge checks for series whose TMDB id changed.

Live 2026-10-26: ~600 series / ~790 movies with a TMDB id still pointed at a
dead provider image host (or a bare TMDB base URL), so cards rendered blank;
and every trickle batch re-checked the same 1,746 different-language pairs."""

import asyncio

import pytest

import tmdb_sync
import vod_importer

TMDB_POSTER = "https://image.tmdb.org/t/p/w500/abc.jpg"


@pytest.fixture()
def poster_env(monkeypatch):
    items = {
        ("series", 1): {"id": 1, "tmdb_id": "89844", "poster_url": "http://dead.invalid/x.jpg"},
        ("series", 2): {"id": 2, "tmdb_id": None, "poster_url": "http://dead.invalid/y.jpg"},
        ("movie", 3): {"id": 3, "tmdb_id": "550", "poster_url": "https://image.tmdb.org/t/p/w600_and_h900_bestv2"},
    }
    saved = []
    fetched = []

    async def details(tmdb_id):
        fetched.append(tmdb_id)
        return {"poster_url": TMDB_POSTER}

    monkeypatch.setattr(vod_importer.vod_db, "get_series", lambda i: items.get(("series", i)))
    monkeypatch.setattr(vod_importer.vod_db, "get_movie", lambda i: items.get(("movie", i)))
    monkeypatch.setattr(vod_importer.vod_db, "bulk_set_poster_url",
                        lambda kind, ids, url: saved.append((kind, ids, url)) or len(ids))
    monkeypatch.setattr(tmdb_sync, "get_series_full_details", details)
    monkeypatch.setattr(tmdb_sync, "get_movie_full_details", details)
    return {"saved": saved, "fetched": fetched}


def test_broken_series_poster_swaps_to_tmdb_and_is_saved(poster_env):
    assert asyncio.run(vod_importer.replace_broken_poster("series", 1)) == TMDB_POSTER
    assert poster_env["fetched"] == ["89844"]
    assert poster_env["saved"] == [("series", [1], TMDB_POSTER)]


def test_broken_movie_poster_swaps_to_tmdb(poster_env):
    assert asyncio.run(vod_importer.replace_broken_poster("movie", 3)) == TMDB_POSTER
    assert poster_env["saved"] == [("movie", [3], TMDB_POSTER)]


def test_no_tmdb_id_leaves_poster_alone(poster_env):
    assert asyncio.run(vod_importer.replace_broken_poster("series", 2)) is None
    assert poster_env["fetched"] == [] and poster_env["saved"] == []


def test_tmdb_without_poster_leaves_poster_alone(poster_env, monkeypatch):
    async def no_poster(tmdb_id):
        return {"poster_url": None}

    monkeypatch.setattr(tmdb_sync, "get_series_full_details", no_poster)
    assert asyncio.run(vod_importer.replace_broken_poster("series", 1)) is None
    assert poster_env["saved"] == []


def test_failing_tmdb_poster_is_not_resaved(poster_env, monkeypatch):
    vod_importer.vod_db.get_series(1)["poster_url"] = TMDB_POSTER
    assert asyncio.run(vod_importer.replace_broken_poster("series", 1)) is None
    assert poster_env["saved"] == []


def test_tmdb_not_found_leaves_poster_alone(poster_env, monkeypatch):
    async def gone(tmdb_id):
        raise tmdb_sync.TmdbNotFoundError(tmdb_id)

    monkeypatch.setattr(tmdb_sync, "get_series_full_details", gone)
    assert asyncio.run(vod_importer.replace_broken_poster("series", 1)) is None
    assert poster_env["saved"] == []


def test_unknown_item_returns_none(poster_env):
    assert asyncio.run(vod_importer.replace_broken_poster("series", 999)) is None


def test_series_tmdb_ids_helper(db):
    provider = db.upsert_provider("XC", "http://xc.invalid", "u", "p")
    db.bulk_import_series(provider, [
        {"name": "A", "year": 2020, "provider_series_id": "1"},
        {"name": "B", "year": 2021, "provider_series_id": "2"},
    ])
    ids = {s["name"]: s["id"] for s in db.list_series(limit=10)}
    conn = db._connect()
    conn.execute("UPDATE series SET tmdb_id='11' WHERE id=?", (ids["A"],))
    conn.commit()
    conn.close()
    assert db.get_series_tmdb_ids({ids["A"], ids["B"]}) == {ids["A"]: "11", ids["B"]: None}
    assert db.get_series_tmdb_ids(set()) == {}


@pytest.fixture()
def trickle_merge_env(monkeypatch):
    providers = [{"id": 1, "name": "P", "is_active": True}]
    pending = [{"id": 100 + i, "series_id": 10 + i, "provider_id": 1} for i in range(3)]
    tmdb = {10: "1", 11: None, 12: "3"}
    swept = {"batch": [], "collisions": []}

    async def fake_enrich(series_id, provider_id, **kwargs):
        if series_id == 11:
            tmdb[11] = "2"  # provider detail supplied a TMDB id
        return {"fetched": True}

    async def fake_sweep(sweep, ids):
        swept["collisions"].append(set(ids))
        return []

    monkeypatch.setattr(vod_importer.vod_db, "list_providers", lambda: providers)
    monkeypatch.setattr(vod_importer.vod_db, "list_pending_series_sources",
                        lambda provider_id, limit=None, series_ids=None: pending)
    monkeypatch.setattr(vod_importer.vod_db, "get_series_episode_summaries", lambda ids: {})
    monkeypatch.setattr(vod_importer.vod_db, "get_series_tmdb_ids", lambda ids: {i: tmdb[i] for i in ids})
    monkeypatch.setattr(vod_importer.vod_db, "auto_merge_series_by_tmdb_batch",
                        lambda ids: swept["batch"].append(set(ids)) or [])
    monkeypatch.setattr(vod_importer, "_run_scoped_collision_sweep", fake_sweep)
    monkeypatch.setattr(vod_importer, "enrich_series_source_only", fake_enrich)
    monkeypatch.setattr(vod_importer, "_provider_backoff_remaining", lambda provider_id: 0.0)
    monkeypatch.setitem(vod_importer._ENRICH_PROGRESS, "running", False)
    return swept


def test_trickle_merges_only_series_whose_tmdb_id_changed(trickle_merge_env):
    asyncio.run(vod_importer.bulk_enrich_series_episodes(concurrency=1))
    assert trickle_merge_env == {"batch": [{11}], "collisions": [{11}]}


def test_trickle_skips_merge_when_no_tmdb_id_changed(trickle_merge_env, monkeypatch):
    async def no_change(series_id, provider_id, **kwargs):
        return {"fetched": True}

    monkeypatch.setattr(vod_importer, "enrich_series_source_only", no_change)
    asyncio.run(vod_importer.bulk_enrich_series_episodes(concurrency=1))
    assert trickle_merge_env == {"batch": [], "collisions": []}


def _owned_episode(db, user_id):
    provider = db.upsert_provider("XC", "http://xc.invalid", "u", "p")
    db.bulk_import_series(provider, [{"name": "Show", "year": 2020, "provider_series_id": "1"}])
    series_id = db.list_series(limit=1)[0]["id"]
    conn = db._connect()
    ep = conn.execute("INSERT INTO episodes (series_id, season_number, episode_number, name, created_at) "
                      "VALUES (?, 1, 1, 'Pilot', '')", (series_id,)).lastrowid
    src = conn.execute("INSERT INTO episode_sources (episode_id, provider_id, provider_stream_id, added_at, last_seen_at) "
                       "VALUES (?, ?, 's1', '', '')", (ep, provider)).lastrowid
    conn.execute("INSERT INTO episode_source_owners (episode_source_id, dispatcharr_user_id, added_at) "
                 "VALUES (?, ?, '')", (src, user_id))
    conn.commit()
    conn.close()
    return series_id


def test_series_owned_by_portal_user(db):
    series_id = _owned_episode(db, user_id=7)
    assert db.series_owned_by_portal_user(series_id, 7) is True
    assert db.series_owned_by_portal_user(series_id, 8) is False


@pytest.fixture()
def portal_env(monkeypatch):
    import portal_routes
    owned = {("movie", 3), ("series", 1)}
    swapped = []

    async def replace(kind, item_id):
        swapped.append((kind, item_id))
        return TMDB_POSTER

    monkeypatch.setattr(portal_routes.vod_db, "movie_owned_by_portal_user", lambda i, u: ("movie", i) in owned)
    monkeypatch.setattr(portal_routes.vod_db, "series_owned_by_portal_user", lambda i, u: ("series", i) in owned)
    monkeypatch.setattr(portal_routes.vod_importer, "replace_broken_poster", replace)
    return portal_routes, swapped


ACCOUNT = {"provider_id": 1, "dispatcharr_user_id": 7}


def test_portal_fallback_swaps_owned_items(portal_env):
    routes, swapped = portal_env
    assert asyncio.run(routes.portal_poster_fallback("series", 1, ACCOUNT)) == {"poster_url": TMDB_POSTER}
    assert asyncio.run(routes.portal_poster_fallback("movie", 3, ACCOUNT)) == {"poster_url": TMDB_POSTER}
    assert swapped == [("series", 1), ("movie", 3)]


def test_portal_fallback_refuses_items_not_in_library(portal_env):
    from fastapi import HTTPException
    routes, swapped = portal_env
    for kind, item_id in (("movie", 99), ("series", 99), ("episode", 1)):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(routes.portal_poster_fallback(kind, item_id, ACCOUNT))
        assert exc.value.status_code == 404
    assert swapped == []
