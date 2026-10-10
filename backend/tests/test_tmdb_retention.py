"""TMDB cache compliance and catalog-first retention."""

import time

import tmdb_store


def _movie_payload(tmdb_id: int, title: str) -> dict:
    return {
        "id": tmdb_id,
        "title": title,
        "original_title": title,
        "release_date": "2020-01-01",
        "genres": [],
        "credits": {"cast": [], "crew": []},
        "release_dates": {"results": []},
        "alternative_titles": {"titles": []},
    }


def _tv_payload(tmdb_id: int, title: str) -> dict:
    return {
        "id": tmdb_id,
        "name": title,
        "original_name": title,
        "first_air_date": "2020-01-01",
        "genres": [],
        "credits": {"cast": [], "crew": []},
        "content_ratings": {"results": []},
        "alternative_titles": {"results": []},
    }


def test_catalog_ids_include_movie_and_series(db):
    provider_id = db.upsert_provider("provider", "http://example.invalid", "u", "p")
    db.bulk_import_movies(provider_id, [{
        "name": "Movie", "year": 2020, "provider_stream_id": "m1",
        "container_extension": "mp4", "tmdb_id": "101", "_has_detail": True,
    }])
    db.bulk_import_series(provider_id, [{
        "name": "Show", "year": 2020, "provider_series_id": "s1",
        "tmdb_id": "202", "_has_detail": True,
    }])

    assert db.list_catalog_tmdb_ids() == {"movie": {101}, "tv": {202}}


def test_retention_preview_then_apply_keeps_only_current_catalog_data(db):
    provider_id = db.upsert_provider("provider", "http://example.invalid", "u", "p")
    db.bulk_import_movies(provider_id, [
        {"name": "Current", "year": 2020, "provider_stream_id": "m1", "container_extension": "mp4", "tmdb_id": "1", "_has_detail": True},
        {"name": "Expired", "year": 2020, "provider_stream_id": "m2", "container_extension": "mp4", "tmdb_id": "2", "_has_detail": True},
    ])
    db.bulk_import_series(provider_id, [{
        "name": "Current Show", "year": 2020, "provider_series_id": "s1", "tmdb_id": "10", "_has_detail": True,
    }])
    tmdb_store.upsert_payload("movie", _movie_payload(1, "Current"))
    tmdb_store.upsert_payload("movie", _movie_payload(2, "Expired"))
    tmdb_store.upsert_payload("movie", _movie_payload(3, "Unreferenced"))
    tmdb_store.upsert_payload("tv", _tv_payload(10, "Current Show"))
    tmdb_store.put_season(10, 1, [{"episode_number": 1}])
    tmdb_store.put_search("search/movie", "old query", None, {"results": [{"id": 3}]}, False)
    tmdb_store.mark_gone("movie", 404)

    old = time.time() - tmdb_store.MAX_CACHE_AGE_SECONDS - 1
    with tmdb_store._conn() as conn:
        conn.execute("UPDATE titles SET fetched_at=? WHERE media_type='movie' AND tmdb_id=2", (old,))
        conn.execute("UPDATE seasons SET fetched_at=? WHERE tmdb_id=10", (old,))
        conn.execute("UPDATE searches SET fetched_at=?", (old,))
        conn.execute("UPDATE gone SET marked_at=?", (old,))

    referenced = db.list_catalog_tmdb_ids()
    preview = tmdb_store.retention_cleanup(referenced)
    assert preview == {
        "dry_run": True,
        "referenced": 3,
        "unreferenced_titles": 1,
        "expired_referenced_titles": 1,
        "seasons_removed": 1,
        "searches_removed": 1,
        "gone_removed": 1,
        "titles_removed": 2,
    }
    assert tmdb_store.get_title("movie", 3) is not None

    applied = tmdb_store.retention_cleanup(referenced, dry_run=False)
    assert applied["titles_removed"] == 2
    assert tmdb_store.get_title("movie", 1) is not None
    assert tmdb_store.get_title("movie", 2) is None
    assert tmdb_store.get_title("movie", 3) is None
    assert tmdb_store.get_title("tv", 10) is not None
    assert tmdb_store.get_season(10, 1) is None
    assert tmdb_store.get_search("search/movie", "old query") is None


def test_retention_removes_fresh_nonempty_searches_and_unreferenced_gone_markers(db):
    tmdb_store.put_search("search/movie", "unrelated", None, {"results": [{"id": 99}]}, False)
    tmdb_store.put_search("search/movie", "empty", None, {"results": []}, True)
    tmdb_store.mark_gone("movie", 404)

    preview = tmdb_store.retention_cleanup({"movie": set(), "tv": set()})
    assert preview["searches_removed"] == 1
    assert preview["gone_removed"] == 1

    tmdb_store.retention_cleanup({"movie": set(), "tv": set()}, dry_run=False)
    assert tmdb_store.get_search("search/movie", "unrelated") is None
    assert tmdb_store.get_search("search/movie", "empty") == {"results": []}


def test_referenced_refresh_queue_includes_missing_changed_and_preexpiry_rows():
    tmdb_store.upsert_payload("movie", _movie_payload(1, "Fresh"))
    tmdb_store.upsert_payload("movie", _movie_payload(2, "Due"))
    tmdb_store.upsert_payload("movie", _movie_payload(3, "Changed"))
    with tmdb_store._conn() as conn:
        conn.execute(
            "UPDATE titles SET fetched_at=? WHERE media_type='movie' AND tmdb_id=2",
            (time.time() - tmdb_store.REFRESH_CACHE_AGE_SECONDS - 1,),
        )
    tmdb_store.mark_changed("movie", [3])

    queued = tmdb_store.list_catalog_refresh_ids("movie", {1, 2, 3, 4}, 10)

    assert queued == [4, 2, 3]


def test_reads_never_serve_data_at_hard_cache_age():
    tmdb_store.upsert_payload("movie", _movie_payload(1, "Expired"))
    tmdb_store.put_search("search/movie", "expired", None, {"results": [{"id": 1}]}, False)
    tmdb_store.put_season(10, 1, [{"episode_number": 1}])
    old = time.time() - tmdb_store.MAX_CACHE_AGE_SECONDS - 1
    with tmdb_store._conn() as conn:
        conn.execute("UPDATE titles SET fetched_at=?", (old,))
        conn.execute("UPDATE searches SET fetched_at=?", (old,))
        conn.execute("UPDATE seasons SET fetched_at=?", (old,))

    assert tmdb_store.get_payload("movie", 1) is None
    assert tmdb_store.get_title("movie", 1) is None
    assert tmdb_store.search("movie", "Expired") == []
    assert tmdb_store.get_search("search/movie", "expired") is None
    assert tmdb_store.get_season(10, 1) is None
