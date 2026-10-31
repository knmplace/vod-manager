"""Provider artwork imports must not persist incomplete TMDB image URLs."""

import vod_db as db


def _series(poster_url, last_modified="1"):
    return {
        "name": "Poster Validation Show",
        "year": 2020,
        "provider_series_id": "show-1",
        "provider_category_name": "Series",
        "raw_name": "Poster Validation Show",
        "_has_detail": True,
        "genre": None,
        "description": None,
        "cast_list": None,
        "director": None,
        "poster_url": poster_url,
        "rating": None,
        "release_date": None,
        "tmdb_id": "12345",
        "provider_last_modified": last_modified,
    }


def test_provider_poster_url_rejects_tmdb_base_without_image_path():
    assert db._usable_provider_poster_url(
        "https://image.tmdb.org/t/p/w600_and_h900_bestv2"
    ) is None
    assert db._usable_provider_poster_url(
        "https://image.tmdb.org/t/p/w500/poster.jpg"
    ) == "https://image.tmdb.org/t/p/w500/poster.jpg"
    assert db._usable_provider_poster_url("https://images.example/poster.jpg") == "https://images.example/poster.jpg"


def test_movie_import_does_not_store_tmdb_base_without_image_path(db):
    provider_id = db.upsert_provider("poster-test", "http://example.com", "user", "pass")
    db.bulk_import_movies(provider_id, [{
        "name": "Poster Validation Movie",
        "year": 2020,
        "provider_stream_id": "movie-1",
        "container_extension": "mp4",
        "poster_url": "https://image.tmdb.org/t/p/w600_and_h900_bestv2",
    }])

    movie = db.get_movie_by_name_year("Poster Validation Movie", 2020)
    assert movie["poster_url"] is None


def test_series_import_preserves_good_poster_when_new_source_art_is_incomplete(db):
    provider_id = db.upsert_provider("poster-test", "http://example.com", "user", "pass")
    good_poster = "https://images.example/good.jpg"
    db.bulk_import_series(provider_id, [_series(good_poster)])

    db.bulk_import_series(provider_id, [_series(
        "https://image.tmdb.org/t/p/w600_and_h900_bestv2", last_modified="2",
    )])

    series = db.get_series_by_name_year("Poster Validation Show", 2020)
    assert series["poster_url"] == good_poster
