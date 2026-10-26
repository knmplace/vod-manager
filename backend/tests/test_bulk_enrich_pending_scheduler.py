"""Scheduled bulk enrichment visits only titles with pending work, merges only
titles it changed, and runs its DB calls on a private pool.

Live 2026-10-26: the daily full pass walked 58,706 movies + 8,755 series for
6,576 s, enriched 1 movie, and re-ran the merge sweeps over the whole catalog
(re-skipping the same 1,746 different-language series pairs)."""

import asyncio
import threading

import pytest

import main
import vod_importer


def _movie(stream_id: str, tmdb_id: str | None) -> dict:
    return {
        "name": f"Movie {stream_id}", "year": 2024,
        "provider_stream_id": stream_id, "container_extension": "mp4",
        "tmdb_id": tmdb_id,
    }


def _ids_by_stream(db) -> dict:
    return {db.list_movie_sources(m["id"])[0]["provider_stream_id"]: m["id"] for m in db.list_movies(limit=50)}


def test_bulk_pending_movie_selector_lists_only_actionable_never_enriched(db):
    xc = db.upsert_provider("XC", "http://xc.invalid", "u", "p")
    other = db.upsert_provider("Other", "http://other.invalid", "u", "p")
    db.bulk_import_movies(xc, [_movie("known", "123"), _movie("unknown", None), _movie("done", "456")])
    db.bulk_import_movies(other, [_movie("elsewhere", "789")])
    ids = _ids_by_stream(db)
    db.set_movie_enrichment(ids["done"])

    assert db.list_movie_ids_pending_bulk_enrichment(xc) == [ids["known"]]
    assert db.list_movie_ids_pending_bulk_enrichment(other) == [ids["elsewhere"]]


def test_bulk_pending_movie_selector_includes_plex_without_tmdb(db):
    plex = db.upsert_provider("Plex", "http://plex.invalid", "u", "p", provider_type="plex")
    db.bulk_import_movies(plex, [_movie("p1", None)])

    assert len(db.list_movie_ids_pending_bulk_enrichment(plex)) == 1


def test_scheduler_runs_pending_only(monkeypatch):
    calls = []

    class _Stop(Exception):
        pass

    async def bulk(**kwargs):
        calls.append(kwargs)

    async def fake_sleep(seconds):
        if calls:
            raise _Stop()

    monkeypatch.setattr(main.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(main.vod_importer, "bulk_enrich_all", bulk)
    monkeypatch.setattr(main.vod_db, "get_enrichment_ttl_seconds", lambda: 3600)
    monkeypatch.setattr(main, "get_last_enrichment_run", lambda: None)
    monkeypatch.setattr(main, "save_last_enrichment_run", lambda t: None)

    with pytest.raises(_Stop):
        asyncio.run(main._vod_enrichment_scheduler())
    assert calls == [{"pending_only": True}]


@pytest.fixture()
def bulk_env(monkeypatch):
    """Full (non-pending) run over movies 10, 11 and series 20, 21; only movie
    10 and series 20 actually change."""
    provider = {"id": 1, "name": "XC", "is_active": True, "provider_type": "xc"}
    swept = {"movie": [], "series": [], "movie_collisions": [], "series_collisions": []}

    async def fake_enrich_movie(movie_id, *, force=False, skip_auto_merge=False, skip_write=False):
        if movie_id == 10:
            return {"movie_id": 10, "fields": {"genre": "x"}, "source_id": None, "bitrate": None}
        return False

    async def fake_series_source_only(series_id, provider_id, **kwargs):
        return {"fetched": series_id == 20, "reason": None}

    async def fake_sweep(sweep, ids):
        key = "movie_collisions" if sweep == "movie" else "series_collisions"
        swept[key].append(set(ids))
        return []

    monkeypatch.setattr(vod_importer, "enrich_movie", fake_enrich_movie)
    monkeypatch.setattr(vod_importer, "enrich_series_source_only", fake_series_source_only)
    monkeypatch.setattr(vod_importer, "_run_scoped_collision_sweep", fake_sweep)
    monkeypatch.setattr(vod_importer.vod_db, "auto_merge_movie_tmdb_collisions", "movie")
    monkeypatch.setattr(vod_importer.vod_db, "auto_merge_series_tmdb_collisions", "series")
    monkeypatch.setattr(vod_importer.vod_db, "list_providers", lambda: [provider])
    monkeypatch.setattr(vod_importer.vod_db, "list_all_movie_ids", lambda **kw: [10, 11])
    monkeypatch.setattr(vod_importer.vod_db, "list_all_series_ids", lambda **kw: [20, 21])
    monkeypatch.setattr(vod_importer.vod_db, "apply_movie_enrichment_batch", lambda items: None)
    monkeypatch.setattr(vod_importer.vod_db, "auto_merge_movies_by_tmdb_batch",
                        lambda ids, should_stop=None: swept["movie"].append(set(ids)))
    monkeypatch.setattr(vod_importer.vod_db, "auto_merge_series_by_tmdb_batch",
                        lambda ids, should_stop=None: swept["series"].append(set(ids)))
    monkeypatch.setitem(vod_importer._ENRICH_PROGRESS, "running", False)
    return swept


def test_merge_sweeps_cover_only_changed_titles(bulk_env):
    asyncio.run(vod_importer.bulk_enrich_all(concurrency=2))

    assert bulk_env["movie"] == [{10}]
    assert bulk_env["series"] == [{20}]
    assert bulk_env["movie_collisions"] == [{10}]
    assert bulk_env["series_collisions"] == [{20}]


def test_merge_sweeps_skip_when_nothing_changed(bulk_env, monkeypatch):
    async def nothing(*a, **kw):
        return False

    async def nothing_series(*a, **kw):
        return {"fetched": False, "reason": "already up to date"}

    monkeypatch.setattr(vod_importer, "enrich_movie", nothing)
    monkeypatch.setattr(vod_importer, "enrich_series_source_only", nothing_series)
    asyncio.run(vod_importer.bulk_enrich_all(concurrency=2))

    assert bulk_env == {"movie": [], "series": [], "movie_collisions": [], "series_collisions": []}


def test_bulk_run_uses_private_pool(bulk_env, monkeypatch):
    names = []

    def list_providers():
        names.append(threading.current_thread().name)
        return []

    monkeypatch.setattr(vod_importer.vod_db, "list_providers", list_providers)
    asyncio.run(vod_importer.bulk_enrich_all(concurrency=2))
    assert names and names[0].startswith("bulk-enrich")


def test_to_thread_outside_bulk_uses_default_pool():
    name = asyncio.run(vod_importer._to_thread(lambda: threading.current_thread().name))
    assert not name.startswith("bulk-enrich")
