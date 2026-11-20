"""Sync History report: per-run card events, delete, and the created/changed
card ids that bulk import reports.

Report layout: @knmplace (PR #35 follow-ups)."""

import sqlite3

import vod_db


def _movie_item(stream_id, name="New Movie", year=2024):
    return {"name": name, "year": year, "provider_stream_id": stream_id,
            "container_extension": "mp4", "raw_name": name}


def test_report_snapshots_changed_cards_and_deletes_only_the_report(db):
    movie_id = db.upsert_movie("New Movie", 2024, tmdb_id="100")
    series_id = db.upsert_series("New Series", 2024, tmdb_id="200")
    run_id = db.create_catalog_sync_run(7, "Provider 7", "xc")

    inserted = db.record_catalog_sync_events(
        run_id, movie_ids=[movie_id], series_ids=[series_id],
        created_movie_ids=[movie_id], created_series_ids=[],
        summary={"movies_created": 1},
    )
    assert inserted == 2
    db.update_catalog_sync_run(run_id, status="ready", summary_json='{"movies_created": 1}')

    [report] = db.list_catalog_sync_runs()
    assert report["id"] == run_id and report["event_count"] == 2
    detail = db.get_catalog_sync_run(run_id)
    actions = {(e["content_type"], e["action"]) for e in detail["events"]}
    assert actions == {("movie", "added"), ("series", "changed")}

    assert db.delete_catalog_sync_runs([run_id, run_id]) == 1
    assert db.get_catalog_sync_run(run_id) is None
    assert db.delete_catalog_sync_runs([run_id]) == 0
    assert db.delete_catalog_sync_runs([]) == 0
    with sqlite3.connect(vod_db.DB_PATH) as conn:
        assert conn.execute("SELECT COUNT(*) FROM catalog_sync_events").fetchone()[0] == 0
    # Catalog content is untouched.
    assert db.get_movie(movie_id)["name"] == "New Movie"
    assert db.get_series(series_id)["name"] == "New Series"


def test_bulk_import_reports_created_and_changed_cards(db):
    provider_id = db.upsert_provider("P", "http://p.invalid", "u", "p")
    first = db.bulk_import_movies(provider_id, [_movie_item("1")])
    assert first["movies_created"] == 1
    assert len(first["created_movie_ids"]) == 1 and first["changed_movie_ids"] == first["created_movie_ids"]

    # Same stream again: nothing new to report.
    again = db.bulk_import_movies(provider_id, [_movie_item("1")])
    assert again["created_movie_ids"] == [] and again["changed_movie_ids"] == []

    # A second source for the same title is a change, not a new card.
    other = db.upsert_provider("Q", "http://q.invalid", "u", "p")
    extra = db.bulk_import_movies(other, [_movie_item("9")])
    assert extra["created_movie_ids"] == []
    assert extra["changed_movie_ids"] == first["created_movie_ids"]


def test_import_result_log_line_reduces_id_lists_to_counts():
    import vod_importer

    result = {"movies_created": 2, "changed_movie_ids": [1, 2, 3], "created_movie_ids": [1, 2], "note": "x"}
    assert vod_importer._loggable_import_result(result) == {
        "movies_created": 2, "changed_movie_ids": 3, "created_movie_ids": 2, "note": "x",
    }
    assert result["changed_movie_ids"] == [1, 2, 3]  # the original is untouched
    assert vod_importer._loggable_import_result(None) is None
