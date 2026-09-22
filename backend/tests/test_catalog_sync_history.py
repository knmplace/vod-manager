"""Regression coverage for persistent, delete-only sync reports."""


def test_sync_report_snapshots_changed_cards_and_deletes_only_report(db):
    movie_id = db.upsert_movie("New Movie", 2024, tmdb_id="100")
    series_id = db.upsert_series("New Series", 2024, tmdb_id="200")
    run_id = db.create_catalog_sync_run(7, "Provider 7")

    inserted = db.record_catalog_sync_events(
        run_id, movie_ids=[movie_id], series_ids=[series_id],
        created_movie_ids=[movie_id], created_series_ids=[series_id],
        summary={"movies_created": 1, "series_created": 1},
    )
    assert inserted == 2
    db.update_catalog_sync_run(run_id, status="ready", summary_json='{"series_created":1}')

    reports = db.list_catalog_sync_runs()
    assert reports[0]["id"] == run_id
    assert reports[0]["event_count"] == 2
    detail = db.get_catalog_sync_run(run_id)
    assert {event["title"] for event in detail["events"]} == {"New Movie", "New Series"}
    assert {event["action"] for event in detail["events"]} == {"added"}

    assert db.delete_catalog_sync_runs([run_id]) == 1
    assert db.get_catalog_sync_run(run_id) is None
    assert db.get_movie(movie_id)["name"] == "New Movie"
    assert db.get_series(series_id)["name"] == "New Series"


def test_sync_report_delete_is_idempotent(db):
    run_id = db.create_catalog_sync_run(None, "No-op")
    assert db.delete_catalog_sync_runs([run_id, run_id]) == 1
    assert db.delete_catalog_sync_runs([run_id]) == 0
