"""KNM: 2026-10-03 needs-review TMDB search used the raw stored name, so
"Title (2014) (US)" returned no candidates for suggestions or AI suggest."""

import asyncio

import tmdb_sync
import vod_routes


def test_default_review_search_strips_year_and_country_suffix(db, monkeypatch):
    series_id = db.upsert_series("BoJack Horseman (2014) (US)", None)
    queries = []

    async def fake_search(query, content_type, year=None):
        queries.append(query)
        return []

    monkeypatch.setattr(tmdb_sync, "search_title", fake_search)
    asyncio.run(vod_routes.year_review_suggestions("series", series_id))
    asyncio.run(vod_routes.year_review_ai_suggest("series", series_id))
    asyncio.run(vod_routes.year_review_suggestions("series", series_id, q="Bojack (2014)"))
    assert queries == ["BoJack Horseman", "BoJack Horseman", "Bojack (2014)"]


def test_default_review_search_strips_quality_prefix_but_preserves_manual_query(db, monkeypatch):
    movie_id = db.upsert_movie("4K: 3:10 to Yuma", None)
    queries = []

    async def fake_search(query, content_type, year=None):
        queries.append((query, content_type, year))
        return []

    monkeypatch.setattr(tmdb_sync, "search_title", fake_search)
    asyncio.run(vod_routes.year_review_suggestions("movie", movie_id))
    asyncio.run(vod_routes.year_review_suggestions("movie", movie_id, q="  4K: A manually entered title  "))

    assert queries == [
        ("3:10 to Yuma", "movie", None),
        ("4K: A manually entered title", "movie", None),
    ]


def test_review_search_query_helper(db):
    assert db.tmdb_review_search_query("Severance (2022) (US)") == "Severance"
    assert db.tmdb_review_search_query("4K: 3:10 to Yuma") == "3:10 to Yuma"
    assert db.tmdb_review_search_query("[1080p] - A Christmas Romance") == "A Christmas Romance"
    assert db.tmdb_review_search_query("4K-DE - Severance (2022)") == "Severance"
    assert db.tmdb_review_search_query("4K Collection") == "4K Collection"
    assert db.tmdb_review_search_query("Plain Title") == "Plain Title"
    assert db.tmdb_review_search_query("Plain Title", "  Other  ") == "Other"
    assert db.tmdb_review_search_query("(2014)") == "(2014)"
