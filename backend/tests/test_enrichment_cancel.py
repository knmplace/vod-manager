import vod_importer


def test_cancel_bulk_enrichment_sets_request_flag():
    original_running = vod_importer._ENRICH_PROGRESS["running"]
    original_cancel = vod_importer._ENRICH_CANCEL_REQUESTED
    try:
        vod_importer._ENRICH_PROGRESS["running"] = True
        vod_importer._ENRICH_CANCEL_REQUESTED = False
        assert vod_importer.cancel_bulk_enrichment() is True
        assert vod_importer._ENRICH_CANCEL_REQUESTED is True
    finally:
        vod_importer._ENRICH_PROGRESS["running"] = original_running
        vod_importer._ENRICH_CANCEL_REQUESTED = original_cancel


def test_cancel_bulk_enrichment_is_noop_when_idle():
    original_running = vod_importer._ENRICH_PROGRESS["running"]
    original_cancel = vod_importer._ENRICH_CANCEL_REQUESTED
    try:
        vod_importer._ENRICH_PROGRESS["running"] = False
        vod_importer._ENRICH_CANCEL_REQUESTED = False
        assert vod_importer.cancel_bulk_enrichment() is False
        assert vod_importer._ENRICH_CANCEL_REQUESTED is False
    finally:
        vod_importer._ENRICH_PROGRESS["running"] = original_running
        vod_importer._ENRICH_CANCEL_REQUESTED = original_cancel


def test_cancel_stops_end_of_run_merge_sweeps(monkeypatch):
    """KNM: 2026-10-13 -- a cancel during the end-of-run auto-merge sweeps used
    to be ignored until every id was merged (a live run had to be stopped with
    docker stop). The sweeps now stop at the next id once cancel is requested."""
    import asyncio

    merged_movies, merged_series, collision_calls = [], [], []

    async def fake_enrich_movie(movie_id, *, force=False, skip_auto_merge=False, skip_write=False):
        return {"movie_id": movie_id, "fields": {}, "source_id": None, "bitrate": None}

    async def fake_enrich_series(*a, **kw):
        return {"fetched": False, "reason": None}

    def fake_merge_movie(movie_id):
        merged_movies.append(movie_id)
        vod_importer._ENRICH_CANCEL_REQUESTED = True  # user hits Stop mid-sweep

    monkeypatch.setattr(vod_importer, "enrich_movie", fake_enrich_movie)
    monkeypatch.setattr(vod_importer, "enrich_series", fake_enrich_series)
    monkeypatch.setattr(vod_importer.vod_db, "apply_movie_enrichment_batch", lambda items: None)
    monkeypatch.setattr(vod_importer.vod_db, "list_providers", lambda: [{"id": 1, "name": "P", "provider_type": "xc"}])
    monkeypatch.setattr(vod_importer.vod_db, "list_all_movie_ids", lambda provider_id=None, **kw: list(range(1, 21)))
    monkeypatch.setattr(vod_importer.vod_db, "list_all_series_ids", lambda **kw: [])
    monkeypatch.setattr(vod_importer.vod_db, "auto_merge_movie_by_tmdb", fake_merge_movie)
    monkeypatch.setattr(vod_importer.vod_db, "auto_merge_series_by_tmdb", lambda sid: merged_series.append(sid))
    monkeypatch.setattr(vod_importer.vod_db, "auto_merge_movie_tmdb_collisions", lambda ids=None: collision_calls.append(ids) or [])
    monkeypatch.setattr(vod_importer.vod_db, "auto_merge_series_tmdb_collisions", lambda ids=None: collision_calls.append(ids) or [])

    try:
        asyncio.run(asyncio.wait_for(vod_importer.bulk_enrich_all(concurrency=4), timeout=10))
    finally:
        vod_importer._ENRICH_CANCEL_REQUESTED = False

    assert len(merged_movies) == 1
    assert merged_series == []
    assert collision_calls == []
    assert vod_importer._ENRICH_PROGRESS["cancelled"] is True
