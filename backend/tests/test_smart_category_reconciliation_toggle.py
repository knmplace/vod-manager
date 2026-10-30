"""Regression coverage for the independent smart-category safety sweep.

The loop is intentionally tested through main._uncategorized_sweep_loop so a
missing get_refresh_settings import cannot be swallowed by the loop's broad
exception handler without failing the enabled-path test.
"""

import asyncio

import config
import main


class _StopAfterFirstSleep(Exception):
    pass


def _run_one_sweep(monkeypatch):
    calls = []

    async def fake_resweep():
        calls.append(True)

    async def stop_after_first_sleep(_seconds):
        raise _StopAfterFirstSleep()

    monkeypatch.setattr(main.vod_importer, "resweep_smart_categories", fake_resweep)
    monkeypatch.setattr(main.asyncio, "sleep", stop_after_first_sleep)
    try:
        asyncio.run(main._uncategorized_sweep_loop())
    except _StopAfterFirstSleep:
        pass
    return calls


def test_smart_category_reconciliation_is_enabled_by_default(db):
    assert config.get_refresh_settings()["smart_category_reconciliation_enabled"] is True


def test_loop_runs_resweep_when_enabled(db, monkeypatch):
    config.save_refresh_settings(3600, 3600, 3600, 3600, 86400, None, True)
    assert _run_one_sweep(monkeypatch) == [True]


def test_loop_skips_resweep_when_disabled(db, monkeypatch):
    config.save_refresh_settings(3600, 3600, 3600, 3600, 86400, None, False)
    assert _run_one_sweep(monkeypatch) == []


def test_smart_category_reconciliation_round_trips(db):
    config.save_refresh_settings(3600, 3600, 3600, 3600, 86400, None, False)
    assert config.get_refresh_settings()["smart_category_reconciliation_enabled"] is False
    config.save_refresh_settings(3600, 3600, 3600, 3600, 86400, None, True)
    assert config.get_refresh_settings()["smart_category_reconciliation_enabled"] is True
