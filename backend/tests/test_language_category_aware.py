# KNM: 2026-10-14 -- the fork's import, backfill and recompute paths called
# _source_language(raw_name) without the provider category, so a tag carried
# only by the category (e.g. "CRUNCHYROLL SERIES (MULTI-SUBS)") was never seen.
# Upstream has passed the category since v0.2.18.

MULTI_CAT = "CRUNCHYROLL SERIES (MULTI-SUBS)"


def _series(db, provider_id, category=MULTI_CAT):
    db.bulk_import_series(provider_id, [{
        "name": "Shadowverse Flame", "year": 2022, "provider_series_id": "cr-1",
        "raw_name": "CR - Shadowverse Flame (2022)", "provider_category_name": category,
        "_has_detail": True,
    }])


def _lang(db):
    conn = db._connect()
    try:
        return conn.execute("SELECT language FROM series_sources").fetchone()["language"]
    finally:
        conn.close()


def _set_lang(db, value):
    conn = db._connect()
    conn.execute("UPDATE series_sources SET language=?", (value,))
    conn.commit()
    conn.close()


def test_series_import_reads_multi_tag_from_category(db):
    _series(db, db.upsert_provider("p", "http://x", "u", "p"))
    assert _lang(db) == "MULTI"


def test_movie_import_reads_multi_tag_from_category(db):
    pid = db.upsert_provider("p", "http://x", "u", "p")
    db.bulk_import_movies(pid, [{
        "name": "Movie A", "year": 2020, "provider_stream_id": "m-1", "container_extension": "mp4",
        "raw_name": "Movie A", "provider_category_name": "ASIA MOVIES (MULTI-SUBS)",
    }])
    conn = db._connect()
    lang = conn.execute("SELECT language FROM movie_sources").fetchone()["language"]
    conn.close()
    assert lang == "MULTI"


def test_recompute_uses_category(db):
    _series(db, db.upsert_provider("p", "http://x", "u", "p"))
    _set_lang(db, "EN")

    report = db.language_recompute_dry_run_report()
    assert report["series_sources"]["MULTI"]["count"] == 1

    assert db.apply_language_recompute() == 1
    assert _lang(db) == "MULTI"
    assert db.apply_language_recompute() == 0


def test_backfill_uses_category(db):
    _series(db, db.upsert_provider("p", "http://x", "u", "p"))
    _set_lang(db, None)

    report = db.language_backfill_dry_run_report()
    assert report["series_sources"]["MULTI"]["count"] == 1

    assert db.apply_language_backfill() == 1
    assert _lang(db) == "MULTI"


def test_title_prefix_still_wins_over_category(db):
    pid = db.upsert_provider("p", "http://x", "u", "p")
    db.bulk_import_series(pid, [{
        "name": "Show", "year": 2022, "provider_series_id": "es-1",
        "raw_name": "ES - Show (2022)", "provider_category_name": MULTI_CAT, "_has_detail": True,
    }])
    assert _lang(db) == "ES"
    assert db.language_recompute_dry_run_report() == {}
