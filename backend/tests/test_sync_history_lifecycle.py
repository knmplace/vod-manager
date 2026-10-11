"""Every catalog importer must leave a final, durable Sync History summary."""

import asyncio

import pytest

import vod_importer


def test_tracked_adapter_import_is_recorded_and_closed(db):
    provider_id = db.upsert_provider("Library A", "http://a.invalid", "u", "p", provider_type="plex")

    async def importer(_provider_id):
        return {"movies_created": 2, "series_matched": 1, "catalog_changed": True}

    result = asyncio.run(vod_importer.run_tracked_import(provider_id, importer))

    report = db.get_catalog_sync_run(result["catalog_sync_run_id"])
    assert report["provider_id"] == provider_id
    assert report["provider_type"] == "plex"
    assert report["status"] == "ready"
    assert report["finished_at"]
    assert report["summary"] == {"movies_created": 2, "series_matched": 1, "catalog_changed": True}


def test_failed_tracked_adapter_import_is_closed(db):
    provider_id = db.upsert_provider("Library B", "http://b.invalid", "u", "p", provider_type="library")

    async def importer(_provider_id):
        raise TimeoutError()

    with pytest.raises(TimeoutError):
        asyncio.run(vod_importer.run_tracked_import(provider_id, importer))

    [report] = db.list_catalog_sync_runs()
    assert report["status"] == "failed"
    assert report["error"] == "TimeoutError"


def test_restart_closes_orphaned_sync_history_run(db):
    run_id = db.create_catalog_sync_run(None, "Interrupted", "xc")

    assert db.close_orphaned_catalog_sync_runs() == 1
    report = db.get_catalog_sync_run(run_id)
    assert report["status"] == "failed"
    assert report["error"] == "interrupted by restart"


def test_xc_import_records_final_summary(db, monkeypatch):
    provider_id = db.upsert_provider("Provider A", "http://a.invalid", "u", "p")

    async def importer(_provider_id):
        return {"movies_created": 1, "catalog_changed": True}

    monkeypatch.setattr(vod_importer, "_import_provider_catalog_impl", importer)
    monkeypatch.setattr(vod_importer, "schedule_known_series_identity_reconciliation", lambda: True)

    result = asyncio.run(vod_importer.import_provider_catalog(provider_id))

    report = db.get_catalog_sync_run(result["catalog_sync_run_id"])
    assert report["status"] == "ready"
    assert report["provider_type"] == "xc"
    assert report["summary"] == {"movies_created": 1, "catalog_changed": True}
