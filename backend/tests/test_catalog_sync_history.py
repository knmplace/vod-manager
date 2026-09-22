"""Regression coverage for persistent, delete-only sync reports."""

import vod_importer


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
    assert detail["events"][0]["detail"]["summary"]["movies_created"] == 1
    assert detail["events"][0]["detail"]["source_count"] == 0

    assert db.delete_catalog_sync_runs([run_id]) == 1
    assert db.get_catalog_sync_run(run_id) is None
    assert db.get_movie(movie_id)["name"] == "New Movie"
    assert db.get_series(series_id)["name"] == "New Series"


def test_sync_report_delete_is_idempotent(db):
    run_id = db.create_catalog_sync_run(None, "No-op")
    assert db.delete_catalog_sync_runs([run_id, run_id]) == 1
    assert db.delete_catalog_sync_runs([run_id]) == 0


def test_sync_report_persists_actionable_episode_event(db):
    series_id = db.upsert_series("Episode Series", 2024, tmdb_id="300")
    run_id = db.create_catalog_sync_run(7, "Provider 7")
    assert db.record_catalog_sync_events(
        run_id,
        extra_events=[{
            "content_type": "series",
            "content_id": series_id,
            "title": "Episode Series",
            "year": 2024,
            "action": "episodes_synced",
            "detail": {
                "episodes_added": 4,
                "episode_sources_added": 2,
                "after": {"episode_count": 4, "season_count": 1},
            },
        }],
    ) == 1
    event = db.get_catalog_sync_run(run_id)["events"][0]
    assert event["action"] == "episodes_synced"
    assert event["detail"]["episodes_added"] == 4
    assert event["detail"]["after"]["season_count"] == 1


def test_workflow_header_hydrates_duration_from_latest_report(db):
    run_id = db.create_catalog_sync_run(7, "Provider 7")
    db.update_catalog_sync_run(
        run_id,
        import_started_at="100.0",
        import_finished_at="132.0",
        enrichment_started_at="132.0",
        enrichment_finished_at="135.0",
        reconciliation_started_at="135.0",
        reconciliation_finished_at="136.0",
        ready_at="136.0",
        status="ready",
    )
    previous = dict(vod_importer._CATALOG_WORKFLOW_PROGRESS)
    try:
        vod_importer._CATALOG_WORKFLOW_PROGRESS.clear()
        vod_importer._CATALOG_WORKFLOW_PROGRESS.update({
            "state": "ready", "run_id": run_id,
            "import_started_at": None, "import_finished_at": None,
            "enrichment_started_at": None, "enrichment_finished_at": None,
            "reconciliation_started_at": None, "reconciliation_finished_at": None,
        })
        progress = vod_importer.get_catalog_workflow_progress()
        assert progress["import_finished_at"] - progress["import_started_at"] == 32
        assert progress["enrichment_finished_at"] - progress["enrichment_started_at"] == 3
        assert progress["reconciliation_finished_at"] - progress["reconciliation_started_at"] == 1
    finally:
        vod_importer._CATALOG_WORKFLOW_PROGRESS.clear()
        vod_importer._CATALOG_WORKFLOW_PROGRESS.update(previous)


def test_workflow_header_retains_hydrated_duration_after_report_delete(db):
    run_id = db.create_catalog_sync_run(7, "Provider 7")
    db.update_catalog_sync_run(
        run_id,
        import_started_at="200.0",
        import_finished_at="232.0",
        ready_at="232.0",
        status="ready",
    )
    previous = dict(vod_importer._CATALOG_WORKFLOW_PROGRESS)
    try:
        vod_importer._CATALOG_WORKFLOW_PROGRESS.clear()
        vod_importer._CATALOG_WORKFLOW_PROGRESS.update({"state": "idle"})
        hydrated = vod_importer.get_catalog_workflow_progress()
        assert hydrated["import_finished_at"] - hydrated["import_started_at"] == 32
        assert db.delete_catalog_sync_runs([run_id]) == 1
        after_delete = vod_importer.get_catalog_workflow_progress()
        assert after_delete["state"] == "ready"
        assert after_delete["import_finished_at"] - after_delete["import_started_at"] == 32
    finally:
        vod_importer._CATALOG_WORKFLOW_PROGRESS.clear()
        vod_importer._CATALOG_WORKFLOW_PROGRESS.update(previous)
