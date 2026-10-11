"""Sync History rows must always reach a final state, every importer type must
write one, and Apply rules must count as a catalog refresh."""

import asyncio
import sqlite3
import time

import pytest

import apply_exclusions_job
import vod_importer


def _fake_xc_impl(changed):
    async def impl(_provider_id):
        return {"catalog_changed": changed, "changed_movie_ids": [], "changed_series_ids": [],
                "created_movie_ids": [], "created_series_ids": []}
    return impl


@pytest.mark.parametrize("changed", [False, True])
def test_deferred_enrichment_xc_import_still_finishes_its_run(db, monkeypatch, changed):
    # The scheduled refresher passes schedule_enrichment=False; the run used
    # to stay "running" forever because only the enrichment path closed it.
    pid = db.upsert_provider("Provider A", "http://a.invalid", "u", "p")
    monkeypatch.setattr(vod_importer, "_import_provider_catalog_impl", _fake_xc_impl(changed))

    result = asyncio.run(vod_importer.import_provider_catalog(pid, schedule_enrichment=False))

    run = db.get_catalog_sync_run(result["catalog_sync_run_id"])
    assert run["status"] == "ready"
    assert run["ready_at"]


def test_library_import_is_recorded_in_sync_history(db):
    pid = db.upsert_provider("Library B", "http://b.invalid", "u", "p", provider_type="plex")

    async def importer(_provider_id):
        return {"catalog_changed": False, "series_created": 0, "movies_created": 2,
                "changed_movie_ids": [], "changed_series_ids": []}

    result = asyncio.run(vod_importer.run_tracked_import(pid, importer))

    run = db.get_catalog_sync_run(result["catalog_sync_run_id"])
    assert run["provider_id"] == pid
    assert run["status"] == "ready"
    assert run["import_finished_at"]
    assert run["summary"]["movies_created"] == 2


def test_failed_library_import_is_recorded_as_failed(db):
    pid = db.upsert_provider("Library C", "http://c.invalid", "u", "p", provider_type="emby")

    async def importer(_provider_id):
        raise TimeoutError()

    with pytest.raises(TimeoutError):
        asyncio.run(vod_importer.run_tracked_import(pid, importer))

    [run] = db.list_catalog_sync_runs()
    assert run["status"] == "failed"
    assert run["error"] == "TimeoutError"


def test_manual_non_xc_import_finish_marks_run_ready(db):
    pid = db.upsert_provider("Library D", "http://d.invalid", "u", "p", provider_type="plex")
    run_id = vod_importer.mark_import_running(pid, "Library D")

    vod_importer.mark_import_finished(pid, run_id=run_id, result={"catalog_changed": False})

    assert db.get_catalog_sync_run(run_id)["status"] == "ready"


def test_orphaned_running_runs_are_closed_on_startup(db):
    finished = db.create_catalog_sync_run(None, "Finished import")
    db.update_catalog_sync_run(finished, import_finished_at="1000.0")
    interrupted = db.create_catalog_sync_run(None, "Interrupted import")

    db.close_orphaned_catalog_sync_runs()

    assert db.get_catalog_sync_run(finished)["status"] == "ready"
    assert db.get_catalog_sync_run(finished)["ready_at"] == "1000.0"
    assert db.get_catalog_sync_run(interrupted)["status"] == "failed"


def test_missing_provider_report_keeps_name_without_foreign_key_failure(db):
    run_id = db.create_catalog_sync_run(999999, "Removed provider")
    run = db.get_catalog_sync_run(run_id)
    assert run["provider_id"] is None
    assert run["provider_name"] == "Removed provider"


def test_failed_report_insert_releases_write_transaction(db, monkeypatch):
    def fail_commit(_conn):
        raise RuntimeError("report commit failed")

    monkeypatch.setattr(db, "_commit_with_retry", fail_commit)
    with pytest.raises(RuntimeError, match="report commit failed"):
        db.create_catalog_sync_run(None, "Report")

    with sqlite3.connect(db.DB_PATH, timeout=0) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.rollback()


def test_report_failure_does_not_replace_import_result(db, monkeypatch):
    pid = db.upsert_provider("Library F", "http://f.invalid", "u", "p", provider_type="plex")

    def fail_report(*_args, **_kwargs):
        raise RuntimeError("report unavailable")

    async def importer(_provider_id):
        return {"catalog_changed": False}

    monkeypatch.setattr(db, "create_catalog_sync_run", fail_report)
    assert asyncio.run(vod_importer.run_tracked_import(pid, importer)) == {"catalog_changed": False}


def test_tracked_import_report_write_does_not_block_event_loop(db, monkeypatch):
    pid = db.upsert_provider("Library G", "http://g.invalid", "u", "p", provider_type="plex")
    original = db.create_catalog_sync_run

    def slow_report(*args, **kwargs):
        time.sleep(0.1)
        return original(*args, **kwargs)

    async def importer(_provider_id):
        return {"catalog_changed": False}

    monkeypatch.setattr(db, "create_catalog_sync_run", slow_report)

    async def run():
        start = time.monotonic()
        async def ticker():
            await asyncio.sleep(0.02)
            return time.monotonic() - start
        result, tick = await asyncio.gather(vod_importer.run_tracked_import(pid, importer), ticker())
        return result, tick

    result, tick = asyncio.run(run())
    assert result["catalog_sync_run_id"]
    assert tick < 0.08


def test_apply_rules_stamps_catalog_refresh_time(db, monkeypatch):
    # Apply rules re-imports every provider; without the stamp the scheduled
    # refresher re-imported the same provider again on its next poll.
    pid = db.upsert_provider("Provider E", "http://e.invalid", "u", "p")

    async def fake_import(_provider_id, **_kwargs):
        return {"catalog_changed": False}

    async def no_resweep(*_args, **_kwargs):
        return None

    monkeypatch.setattr(vod_importer, "import_provider_catalog", fake_import)
    monkeypatch.setattr(vod_importer, "resweep_smart_categories", no_resweep)
    apply_exclusions_job._jobs["t"] = {"status": "running", "total": 0, "completed": 0,
                                       "current_provider": None, "results": [], "error": None,
                                       "started_at": 0}
    try:
        asyncio.run(apply_exclusions_job._run_job("t"))
    finally:
        apply_exclusions_job._jobs.pop("t", None)

    assert db.get_provider(pid)["last_catalog_refresh_at"]
