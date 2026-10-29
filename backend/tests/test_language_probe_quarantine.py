"""Language probe failures rotate once, then quarantine for manual action."""

import vod_db


def _movie(db, provider_id, stream_id):
    return db.bulk_import_movies(provider_id, [{
        "name": "Rotation Movie", "year": 2026,
        "provider_stream_id": stream_id, "container_extension": "mp4",
        "provider_category_name": "Movies",
    }])


def test_first_failure_moves_source_behind_unfailed_source_and_second_quarantines(db):
    first_provider = db.upsert_provider("Provider A", "http://a.invalid", "u", "p", priority=10)
    second_provider = db.upsert_provider("Provider B", "http://b.invalid", "u", "p")
    _movie(db, first_provider, "a-source")
    _movie(db, second_provider, "b-source")
    movie = db.get_movie_by_name_year("Rotation Movie", 2026)
    sources = db.list_movie_sources(movie["id"])
    first = next(s for s in sources if s["provider_id"] == first_provider)

    assert [s["provider_stream_id"] for s in db.list_movie_sources_for_streaming(movie["id"])] == ["a-source", "b-source"]
    db.record_language_probe_failure("movie", first["id"], "HTTP 400")
    assert [s["provider_stream_id"] for s in db.list_movie_sources_for_streaming(movie["id"])] == ["b-source", "a-source"]

    db.record_language_probe_failure("movie", first["id"], "HTTP 400")
    assert [s["provider_stream_id"] for s in db.list_movie_sources_for_streaming(movie["id"])] == ["b-source"]
    errors = db.list_language_probe_errors()
    assert errors[0]["source_id"] == first["id"]
    assert errors[0]["attempts"] == 2


def test_retry_clears_quarantine_and_delete_removes_source(db):
    provider_id = db.upsert_provider("Provider A", "http://a.invalid", "u", "p")
    _movie(db, provider_id, "a-source")
    movie = db.get_movie_by_name_year("Rotation Movie", 2026)
    source = db.list_movie_sources(movie["id"])[0]
    db.record_language_probe_failure("movie", source["id"], "HTTP 400")
    db.record_language_probe_failure("movie", source["id"], "HTTP 400")
    db.reset_language_probe_failure("movie", source["id"])
    assert db.list_language_probe_errors() == []
    assert db.get_language_probe_source("movie", source["id"])["language_probe_failures"] == 0

    db.record_language_probe_failure("movie", source["id"], "HTTP 400")
    db.record_language_probe_failure("movie", source["id"], "HTTP 400")
    db.delete_language_probe_source("movie", source["id"])
    assert db.get_movie_by_name_year("Rotation Movie", 2026) is None
