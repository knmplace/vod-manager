"""Library language filter, Missing Artwork picker and smart exclude read the
source's provider language, not the card name: Title & Metadata Rules strip
"ES|"-style prefixes from card names, which made every card look EN."""

from test_import_policy_sweep import _movie_source, _provider


def _stripped_es_card(db):
    provider_id = _provider(db, "xc")
    movie_id = db.upsert_movie("Apex", 2020)  # rules stripped "ES| "
    _movie_source(db, movie_id, provider_id, "es-1", "ES| Apex", "ES")
    return provider_id, movie_id


def test_library_prefixes_and_filter_use_source_language(db):
    _, movie_id = _stripped_es_card(db)
    codes = {row["code"]: row["count"] for row in db.list_library_prefixes("movie")}
    assert codes.get("ES") == 1 and "EN" not in codes
    assert [r["id"] for r in db.list_library_filtered("movie", prefixes=["ES"])] == [movie_id]
    assert db.list_library_filtered("movie", prefixes=["EN"]) == []


def test_missing_artwork_prefixes_and_filter_use_source_language(db):
    _, movie_id = _stripped_es_card(db)
    assert {row["code"] for row in db.list_missing_artwork_prefixes("movie")} == {"ES"}
    assert [r["id"] for r in db.list_missing_artwork("movie", prefixes=["ES"])] == [movie_id]


def test_missing_artwork_includes_bare_tmdb_urls_and_hides_adults_by_default(db):
    bare = db.upsert_movie("Bare TMDB", 2020)
    adult = db.upsert_movie("Adult Missing", 2020)
    valid = db.upsert_movie("Has Poster", 2020)
    conn = db._connect()
    conn.execute("UPDATE movies SET poster_url='https://image.tmdb.org/t/p/w500', is_adult=0 WHERE id=?", (bare,))
    conn.execute("UPDATE movies SET is_adult=1 WHERE id=?", (adult,))
    conn.execute("UPDATE movies SET poster_url='https://image.tmdb.org/t/p/w500/poster.jpg' WHERE id=?", (valid,))
    conn.commit()
    conn.close()
    assert {row["id"] for row in db.list_missing_artwork("movie")} == {bare}
    assert {row["id"] for row in db.list_missing_artwork("movie", hide_adult=False)} == {bare, adult}


def test_missing_artwork_resolution_saves_poster_and_identity(db):
    movie_id = db.upsert_movie("Aussie Road Train Truckers", 2025)
    result = db.resolve_missing_artwork(
        "movie", movie_id, "https://image.tmdb.org/t/p/w185/poster.jpg", "12345",
        "Aussie Road Train Truckers", 2025,
    )
    saved = db.get_movie(movie_id)
    assert result == {"resolved_id": movie_id}
    assert saved["poster_url"].endswith("/poster.jpg")
    assert saved["tmdb_id"] == "12345" and saved["year"] == 2025


def test_card_without_sources_falls_back_to_name(db):
    db.upsert_movie("AR| Legacy", 2019)
    assert {row["code"] for row in db.list_library_prefixes("movie")} == {"AR"}


def test_smart_exclude_judges_siblings_by_source_language(db):
    provider_id = _provider(db, "xc")
    arabic = db.upsert_movie("Apex", 2020)
    _movie_source(db, arabic, provider_id, "ar-1", "AR| Apex", "AR")
    french = db.upsert_movie("Apex", 2005)
    _movie_source(db, french, provider_id, "fr-1", "FR| Apex", "FR")
    # The only sibling is French, which isn't a kept language: keep the Arabic copy.
    assert db.smart_bulk_exclude("movie", [arabic], ["EN"], dry_run=True)["archived"] == 0
    english = db.upsert_movie("Apex", 1990)
    _movie_source(db, english, provider_id, "en-1", "Apex", "EN")
    assert db.smart_bulk_exclude("movie", [arabic], ["EN"], dry_run=True)["archived"] == 1
