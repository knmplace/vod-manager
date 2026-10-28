"""list_metadata_review surfaces the broader identity-gap queue (missing
both tmdb_id and year, or held by the older ambiguous-year detector) that
backs the sidebar's Metadata Review tab -- a superset of
list_needs_year_review's narrower needs_year_review=1 condition. The
runtime-status progress helpers (get_import_progress, get_process_cpu_percent,
get_active_bulk_ai_status) back the sidebar's live status indicator.
"""

import vod_bulk_ai_service
import vod_importer


def test_actionable_gap_without_year_review_flag_is_included(db):
    provider_id = db.upsert_provider("XC-Test", "http://example.com", "user", "pass")
    db.bulk_import_movies(provider_id, [
        {"name": "No Identity At All", "year": None, "provider_stream_id": "1", "container_extension": "mkv"},
    ])

    review = db.list_metadata_review("movie")
    names = {m["name"] for m in review["movies"]}
    assert "No Identity At All" in names


def test_row_with_year_but_no_tmdb_id_is_included(db):
    provider_id = db.upsert_provider("XC-Test", "http://example.com", "user", "pass")
    db.bulk_import_movies(provider_id, [
        {"name": "Has A Year", "year": 2020, "provider_stream_id": "1", "container_extension": "mkv"},
    ])

    review = db.list_metadata_review("movie")
    names = {m["name"] for m in review["movies"]}
    assert "Has A Year" in names


def test_archived_row_is_excluded(db):
    movie_id = db.upsert_movie("Gapped But Archived", None)
    db.bulk_set_review_excluded("movie", [movie_id], True)

    review = db.list_metadata_review("movie")
    names = {m["name"] for m in review["movies"]}
    assert "Gapped But Archived" not in names


def test_content_type_filter_scopes_to_one_table(db):
    db.upsert_provider("XC-Test", "http://example.com", "user", "pass")
    db.upsert_movie("Gapped Movie", None)
    db.upsert_series("Gapped Series", None)

    movies_only = db.list_metadata_review("movie")
    assert "movies" in movies_only
    assert "series" not in movies_only


def test_get_import_progress_defaults_idle():
    progress = vod_importer.get_import_progress()
    assert progress["running"] is False


def test_get_process_cpu_percent_first_call_returns_none_or_float():
    # First sample has no prior baseline -- None is the correct answer, not
    # an error; a later call in the same process could return a float.
    result = vod_importer.get_process_cpu_percent()
    assert result is None or isinstance(result, float)


def test_get_active_bulk_ai_status_defaults_idle():
    status = vod_bulk_ai_service.get_active_bulk_ai_status()
    assert status == {"running": False, "done": 0, "total": 0, "jobs": 0}


def test_bulk_ai_job_can_be_cancelled_before_next_item():
    job_id = vod_bulk_ai_service._new_job(2)

    assert vod_bulk_ai_service.cancel_bulk_ai_job(job_id) is True
    job = vod_bulk_ai_service.get_bulk_ai_job(job_id)
    assert job["running"] is False
    assert job["cancelled"] is True
    assert job["error"] == "Cancelled by user"
    assert vod_bulk_ai_service.get_active_bulk_ai_status()["running"] is False


def test_bulk_ai_confident_yearless_pick_sets_tmdb_id(db, monkeypatch):
    """A confident TMDB pick with no release year (unreleased/new title) used to
    be skipped; it now sets the TMDB ID alone, which clears the review row."""
    import asyncio
    import ai_assist
    import tmdb_sync

    provider_id = db.upsert_provider("XC-Test", "http://example.com", "user", "pass")
    db.bulk_import_movies(provider_id, [
        {"name": "Arthurs Empire", "year": None, "provider_stream_id": "1", "container_extension": "mkv"},
    ])
    item_id = db.list_metadata_review("movie")["movies"][0]["id"]

    async def fake_search(query, content_type):
        return [{"tmdb_id": "999001", "name": "Arthurs Empire", "year": None}]

    async def fake_suggest(*args, **kwargs):
        return {"best_match_index": 0, "confidence": "high", "reasoning": "exact"}

    monkeypatch.setattr(tmdb_sync, "search_title", fake_search)
    monkeypatch.setattr(ai_assist, "suggest_year_review_match", fake_suggest)

    result = asyncio.run(vod_bulk_ai_service._resolve_one_needs_review("movie", item_id))

    assert result["status"] == "resolved"
    assert str(db.get_movie(item_id)["tmdb_id"]) == "999001"
    assert not db.list_metadata_review("movie")["movies"]
