"""Scheduled/manual bulk enrichment must never call a provider's
get_series_info. Episodes come only from the paced episode trickle and from
on-demand open/play (enrich_series). Live 2026-10-11: a scheduled run made
10,088 get_series_info calls."""

import asyncio

import pytest

import vod_importer

XC_PROVIDER = {"id": 1, "name": "XC One", "is_active": True, "provider_type": "xc"}
SERIES = {"id": 20, "name": "Show", "provider_last_modified": "1700000000"}
NEVER_FETCHED = {"id": 200, "series_id": 20, "provider_id": 1, "provider_series_id": "555", "last_seen_at": None}


@pytest.fixture()
def xc_env(monkeypatch):
    calls: list[str] = []

    class FakeClient:
        def __init__(self, provider):
            pass

        async def get_series_info(self, provider_series_id):
            calls.append(provider_series_id)
            return {"episodes": {}}

    async def noop_movie(*a, **kw):
        return None

    async def noop_sweep(*a, **kw):
        return []

    monkeypatch.setattr(vod_importer, "XCProviderClient", FakeClient)
    monkeypatch.setattr(vod_importer, "enrich_movie", noop_movie)
    monkeypatch.setattr(vod_importer, "_run_scoped_collision_sweep", noop_sweep)
    monkeypatch.setattr(vod_importer.vod_db, "list_providers", lambda: [XC_PROVIDER])
    monkeypatch.setattr(vod_importer.vod_db, "get_provider", lambda pid: XC_PROVIDER)
    monkeypatch.setattr(vod_importer.vod_db, "list_all_movie_ids", lambda **kw: [])
    monkeypatch.setattr(vod_importer.vod_db, "list_all_series_ids", lambda **kw: [20])
    monkeypatch.setattr(vod_importer.vod_db, "get_series", lambda sid: dict(SERIES))
    monkeypatch.setattr(vod_importer.vod_db, "list_series_sources", lambda sid: [dict(NEVER_FETCHED)])
    monkeypatch.setattr(vod_importer.vod_db, "series_existing_sources_due", lambda series: True)
    monkeypatch.setattr(vod_importer.vod_db, "series_source_needs_enrichment", lambda source, due=False: True)
    monkeypatch.setattr(vod_importer.vod_db, "series_needs_enrichment", lambda sid: True)
    monkeypatch.setattr(vod_importer.vod_db, "list_episode_keys", lambda sid, pid: set())
    monkeypatch.setattr(vod_importer.vod_db, "enrich_series_episodes_batch", lambda *a: None)
    monkeypatch.setattr(vod_importer.vod_db, "set_series_source_enrichment", lambda *a: None)
    monkeypatch.setattr(vod_importer.vod_db, "set_series_enrichment", lambda *a, **kw: None)
    monkeypatch.setattr(vod_importer.vod_db, "auto_merge_movies_by_tmdb_batch", lambda ids, should_stop=None: None)
    monkeypatch.setattr(vod_importer.vod_db, "auto_merge_series_by_tmdb_batch", lambda ids, should_stop=None: None)
    monkeypatch.setitem(vod_importer._ENRICH_PROGRESS, "running", False)
    return calls


@pytest.mark.parametrize("force", [False, True])
def test_bulk_enrich_all_never_calls_get_series_info(xc_env, force):
    asyncio.run(vod_importer.bulk_enrich_all(concurrency=2, force=force))
    assert xc_env == []


def test_on_demand_series_enrich_still_fetches_episodes(xc_env):
    asyncio.run(vod_importer.enrich_series(20))
    assert xc_env == ["555"]


def test_trickle_lane_still_fetches_pending_source(xc_env, monkeypatch):
    monkeypatch.setattr(vod_importer.vod_db, "list_pending_series_sources", lambda pid, *a, **kw: [dict(NEVER_FETCHED)])
    monkeypatch.setattr(vod_importer.vod_db, "get_series_episode_summaries", lambda *a, **kw: {})
    monkeypatch.setattr(vod_importer.vod_db, "auto_merge_series_tmdb_collisions", lambda ids=None: [])
    monkeypatch.setattr(vod_importer, "_provider_backoff_remaining", lambda provider_id: 0.0)

    async def no_sleep(seconds):
        return None

    monkeypatch.setattr(vod_importer, "_trickle_sleep", no_sleep)
    asyncio.run(vod_importer.run_episode_trickle_tick(batch_size=5, spacing_seconds=0))
    assert xc_env == ["555"]
