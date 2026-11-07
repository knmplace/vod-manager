"""Old probe history is folded into daily totals so the table stays small but the report is unchanged."""
import time


def _insert_run(db, pid, age_days, status="observed", mismatch=0, wanted=0):
    conn = db._connect()
    conn.execute("""INSERT INTO language_probe_runs (kind, source_id, provider_id, checked_at, status,
                    wanted_languages, mismatch, wanted_match) VALUES ('movie', 1, ?, ?, ?, '[]', ?, ?)""",
                 (pid, str(time.time() - age_days * 86400), status, mismatch, wanted))
    conn.commit()
    conn.close()


def _count(db, table):
    conn = db._connect()
    n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    conn.close()
    return n


def test_rollup_moves_old_rows_and_keeps_report_totals(db):
    pid = db.upsert_provider("P", "http://p.invalid", "u", "p")
    for _ in range(3):
        _insert_run(db, pid, 20)
    _insert_run(db, pid, 20, mismatch=1, wanted=1)
    _insert_run(db, pid, 20, status="deferred")
    _insert_run(db, pid, 1)
    before = db.language_audit_stats()
    moved = db.rollup_language_probe_history(keep_days=14)
    assert moved == 5
    assert _count(db, "language_probe_runs") == 1
    after = db.language_audit_stats()
    assert after["history"] == before["history"]
    assert after["provider_history"] == before["provider_history"]
    assert db.rollup_language_probe_history(keep_days=14) == 0  # idempotent


def test_rollup_merges_into_existing_day(db):
    pid = db.upsert_provider("P", "http://p.invalid", "u", "p")
    _insert_run(db, pid, 20)
    db.rollup_language_probe_history(keep_days=14)
    _insert_run(db, pid, 20)
    db.rollup_language_probe_history(keep_days=14)
    day = db.language_audit_stats()["history"]
    assert sum(r["probes"] for r in day) == 2


def test_hourly_housekeeping_logs_summary_and_rolls_up(monkeypatch, caplog):
    import logging
    import vod_probe
    calls = []
    monkeypatch.setattr(vod_probe.vod_db, "rollup_language_probe_history", lambda: calls.append(1) or 7)
    tally = {"checked": 3, "deferred": 2}
    caplog.set_level(logging.INFO)
    assert vod_probe._language_housekeeping(tally, last=0.0, now=10.0) == 0.0  # not an hour yet
    assert not calls
    assert vod_probe._language_housekeeping(tally, last=0.0, now=3601.0) == 3601.0
    assert calls == [1] and tally == {}
    assert "checked=3" in caplog.text and "deferred=2" in caplog.text
