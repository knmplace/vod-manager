"""2026-09-11 follow-up: list_all_pool_prefixes() only counted titles with a
literal language-style name prefix ("GR - Title", "AR|Title", ...), so the
vast majority of untagged titles -- which vod_db._source_language already
treats as "EN" by default -- were invisible to the Import Language Exclusion
/ Enabled Playback Languages pickers. That made the pool look almost empty
(a real deployment with ~87k titles showed only 6 total) and made "EN"
impossible to select/exclude even though it's what most untagged content
actually is. Fixed by having list_all_pool_prefixes/list_library_prefixes
(and the _should_auto_archive / _row_excluded_by_rule matchers they
back) treat "no recognized prefix" as "EN", matching _source_language's
existing fallback."""


def _import_movie(db, provider_id, name, stream_id, raw_name, tmdb_id):
    db.bulk_import_movies(provider_id, [
        {
            "name": name,
            "year": 2001,
            "provider_stream_id": stream_id,
            "container_extension": "mp4",
            "raw_name": raw_name,
            "tmdb_id": tmdb_id,
            "_has_detail": True,
        },
    ])


def test_untagged_titles_counted_as_en(db):
    provider_id = db.upsert_provider("prov1", "http://example.com", "user", "pass")
    _import_movie(db, provider_id, "Amelie", "en-1", "Amelie", tmdb_id=194)
    _import_movie(db, provider_id, "GR - Some Movie", "gr-1", "GR - Some Movie", tmdb_id=195)

    counts = {p["code"]: p["count"] for p in db.list_all_pool_prefixes()}
    assert counts["EN"] == 1
    assert counts["GR"] == 1


def test_all_untagged_pool_shows_en_not_empty(db):
    provider_id = db.upsert_provider("prov1", "http://example.com", "user", "pass")
    for i in range(5):
        _import_movie(db, provider_id, f"Movie {i}", f"en-{i}", f"Movie {i}", tmdb_id=100 + i)

    counts = {p["code"]: p["count"] for p in db.list_all_pool_prefixes()}
    assert counts == {"EN": 5}


def test_rule_stripped_display_name_counts_source_language(db):
    # KNM: 2026-10-11 -- Title & Metadata Rules strip "ES - " from the card
    # name; the picker must still see ES via the source's raw_name.
    provider_id = db.upsert_provider("prov1", "http://example.com", "user", "pass")
    _import_movie(db, provider_id, "3 dias en Malay", "es-1", "ES - 3 dias en Malay", tmdb_id=300)
    _import_movie(db, provider_id, "Amelie", "en-1", "Amelie", tmdb_id=194)

    counts = {p["code"]: p["count"] for p in db.list_all_pool_prefixes()}
    assert counts == {"ES": 1, "EN": 1}


def test_card_with_sources_in_two_languages_counts_under_each(db):
    p1 = db.upsert_provider("prov1", "http://example.com", "user", "pass")
    p2 = db.upsert_provider("prov2", "http://example2.com", "user", "pass")
    _import_movie(db, p1, "Heat", "en-1", "EN| Heat", tmdb_id=949)
    _import_movie(db, p2, "Heat", "es-1", "ES| Heat", tmdb_id=949)

    counts = {p["code"]: p["count"] for p in db.list_all_pool_prefixes()}
    assert counts == {"EN": 1, "ES": 1}
