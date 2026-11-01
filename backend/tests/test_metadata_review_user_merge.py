import asyncio

import tmdb_sync
import vod_bulk_ai_service


def test_user_merge_applies_the_only_tmdb_candidate_without_ai(db, monkeypatch):
    keep_id = db.upsert_movie("Known Title", 2020, tmdb_id="123")
    incoming_id = db.upsert_movie("Imported Alias", None)

    async def only_candidate(query, content_type):
        return [{"tmdb_id": "123", "name": "Known Title", "year": 2020}]

    monkeypatch.setattr(tmdb_sync, "search_title", only_candidate)
    monkeypatch.setattr(
        "ai_assist.suggest_year_review_match",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("User Merge must not call AI")),
    )

    result = asyncio.run(vod_bulk_ai_service._user_merge_one_needs_review("movie", incoming_id))

    assert result["status"] == "resolved"
    assert f"#{keep_id}" in result["detail"]
    assert db.get_movie(incoming_id) is None
    assert db.get_movie(keep_id) is not None


def test_user_merge_applies_unique_candidate_when_no_catalog_duplicate_exists(db, monkeypatch):
    item_id = db.upsert_movie("Single Result", None)

    async def only_candidate(query, content_type):
        return [{"tmdb_id": "456", "name": "Single Result", "year": 2019}]

    monkeypatch.setattr(tmdb_sync, "search_title", only_candidate)

    result = asyncio.run(vod_bulk_ai_service._user_merge_one_needs_review("movie", item_id))

    assert result["status"] == "resolved"
    assert result["detail"] == "user-approved TMDB candidate applied; no existing duplicate was merged"
    assert db.get_movie(item_id)["year"] == 2019
    assert str(db.get_movie(item_id)["tmdb_id"]) == "456"


def test_user_merge_skips_ambiguous_candidates_without_changing_identity(db, monkeypatch):
    item_id = db.upsert_movie("Ambiguous Title", None)

    async def two_candidates(query, content_type):
        return [
            {"tmdb_id": "201", "name": "Ambiguous Title", "year": 2020},
            {"tmdb_id": "202", "name": "Ambiguous Title", "year": 2021},
        ]

    monkeypatch.setattr(tmdb_sync, "search_title", two_candidates)

    result = asyncio.run(vod_bulk_ai_service._user_merge_one_needs_review("movie", item_id))

    assert result["status"] == "skipped"
    assert "found 2" in result["detail"]
    assert db.get_movie(item_id)["tmdb_id"] is None


def test_user_merge_skips_when_tmdb_has_no_candidate(db, monkeypatch):
    item_id = db.upsert_movie("No Candidate", None)

    async def no_candidates(query, content_type):
        return []

    monkeypatch.setattr(tmdb_sync, "search_title", no_candidates)

    result = asyncio.run(vod_bulk_ai_service._user_merge_one_needs_review("movie", item_id))

    assert result["status"] == "skipped"
    assert result["detail"] == "no TMDB candidates found"
    assert db.get_movie(item_id)["tmdb_id"] is None
