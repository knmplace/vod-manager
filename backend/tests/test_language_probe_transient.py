"""Failed/timed-out checks leave playback until a person or an automatic recheck clears them."""
import asyncio
import time

import config
import vod_probe


def _movie_source(db, provider_id, title):
    category_id = db.upsert_category("Movies", "movie")
    movie_id = db.upsert_movie(title, 2026)
    db.place_movie_in_category(movie_id, category_id)
    db.add_movie_source(movie_id, provider_id, title, "mp4")
    conn = db._connect()
    sid = conn.execute("SELECT id FROM movie_sources WHERE movie_id=?", (movie_id,)).fetchone()["id"]
    conn.close()
    return movie_id, sid


def _row(db, sid):
    conn = db._connect()
    row = dict(conn.execute("SELECT * FROM movie_sources WHERE id=?", (sid,)).fetchone())
    conn.close()
    return row


def _provider_answered(db, pid):
    db.record_language_probe_run("movie", 999999, pid, "observed", "EN", ["EN"], ["EN"], False, True)


def _make_recheck_due(db, sid):
    conn = db._connect()
    conn.execute("UPDATE movie_sources SET language_probe_recheck_at=? WHERE id=?", (time.time() - 1, sid))
    conn.commit()
    conn.close()


def test_trickle_timeout_is_counted_and_second_one_quarantines(db, monkeypatch):
    config.save_language_trickle_settings(15, 180, None)
    pid = db.upsert_provider("Slow", "http://slow.invalid", "u", "p")
    movie_id, sid = _movie_source(db, pid, "Slow Movie")
    _provider_answered(db, pid)

    async def timeout(*a, **k):
        raise vod_probe.ProbeRefused("Slow took too long to answer.", 60, "transient")

    monkeypatch.setattr(vod_probe, "probe_language_source", timeout)
    target = {"kind": "movie", "source_id": sid, "provider_id": pid}
    assert asyncio.run(vod_probe.language_trickle_once(target))["status"] == "deferred"
    assert _row(db, sid)["language_probe_transient_failures"] == 1
    assert db.list_movie_sources_for_streaming(movie_id)  # one blip: still playable

    assert asyncio.run(vod_probe.language_trickle_once(target))["status"] == "quarantined"
    row = _row(db, sid)
    assert row["language_probe_quarantined_at"] is not None
    assert row["language_probe_recheck_at"] > time.time() + 86000
    assert db.list_movie_sources_for_streaming(movie_id) == []
    errors = db.list_language_probe_errors()
    assert errors[0]["source_id"] == sid and errors[0]["attempts"] == 2 and errors[0]["next_recheck_at"]


def test_provider_outage_does_not_quarantine_but_backs_off(db):
    pid = db.upsert_provider("Down", "http://down.invalid", "u", "p")
    movie_id, bad = _movie_source(db, pid, "Bad Movie")
    _, good = _movie_source(db, pid, "Good Movie")
    db.record_language_probe_transient_failure("movie", bad, "timeout", pid)
    assert [t["source_id"] for t in db.next_language_probe_targets(10, False)] == [good, bad]
    for _ in range(db.LANGUAGE_TRANSIENT_LIMIT - 1):
        result = db.record_language_probe_transient_failure("movie", bad, "timeout", pid)
    assert result["quarantined"] is False
    assert db.list_movie_sources_for_streaming(movie_id)
    assert [t["source_id"] for t in db.next_language_probe_targets(10, False)] == [good]
    conn = db._connect()
    conn.execute("UPDATE movie_sources SET language_probe_transient_at=? WHERE id=?",
                 (time.time() - db.LANGUAGE_TRANSIENT_BACKOFF_SECONDS - 1, bad))
    conn.commit()
    conn.close()
    assert bad in [t["source_id"] for t in db.next_language_probe_targets(10, False)]


def test_quarantined_source_is_rechecked_when_due_and_success_restores_playback(db):
    pid = db.upsert_provider("Slow", "http://slow.invalid", "u", "p")
    movie_id, sid = _movie_source(db, pid, "Slow Movie")
    _, other = _movie_source(db, pid, "Other Movie")
    _provider_answered(db, pid)
    db.record_language_probe_transient_failure("movie", sid, "timeout", pid)
    db.record_language_probe_transient_failure("movie", sid, "timeout", pid)
    assert [t["source_id"] for t in db.next_language_probe_targets(10, False)] == [other]
    _make_recheck_due(db, sid)
    assert [t["source_id"] for t in db.next_language_probe_targets(10, False)][0] == sid  # due recheck goes first
    # a failed recheck waits longer next time
    db.record_language_probe_transient_failure("movie", sid, "timeout", pid)
    assert _row(db, sid)["language_probe_recheck_at"] > time.time() + 2 * 86400 - 60
    _make_recheck_due(db, sid)
    db.set_source_language_probe("movie", sid, ["EN"], "observed", "embedded_audio_tags", "high")
    row = _row(db, sid)
    assert row["language_probe_quarantined_at"] is None and row["language_probe_transient_failures"] == 0
    assert row["language_probe_recheck_at"] is None
    assert db.list_movie_sources_for_streaming(movie_id)


def test_provider_error_quarantine_also_schedules_recheck(db):
    pid = db.upsert_provider("Broken", "http://broken.invalid", "u", "p")
    _, sid = _movie_source(db, pid, "Broken Movie")
    db.record_language_probe_failure("movie", sid, "HTTP 404")
    assert _row(db, sid)["language_probe_recheck_at"] is None
    db.record_language_probe_failure("movie", sid, "HTTP 404")
    assert _row(db, sid)["language_probe_recheck_at"] > time.time()
    db.reset_language_probe_failure("movie", sid)
    assert _row(db, sid)["language_probe_recheck_at"] is None


def test_claimed_set_keys_by_kind_and_source(monkeypatch):
    monkeypatch.setattr(config, "get_language_trickle_settings", lambda: {
        "language_trickle_enabled": True, "language_trickle_probes_per_cycle": 10,
        "language_trickle_interval_seconds": 90, "language_trickle_daily_limit": None})
    targets = [{"kind": "movie", "source_id": 5, "provider_id": 1},
               {"kind": "episode", "source_id": 5, "provider_id": 2}]
    seen = []

    async def once(target):
        seen.append((target["kind"], target["source_id"]))
        return {"status": "checked", "result": {"source_id": target["source_id"]}}

    monkeypatch.setattr(vod_probe.vod_db, "next_language_probe_targets", lambda *a: targets)
    monkeypatch.setattr(vod_probe.vod_db, "language_probe_provider_states", lambda *a: [])
    monkeypatch.setattr(vod_probe, "language_trickle_once", once)
    monkeypatch.setattr(vod_probe, "language_trickle_status", lambda: {})
    vod_probe._language_claimed_sources.add((("movie", 5)))
    try:
        asyncio.run(vod_probe.run_language_trickle_cycle())
    finally:
        vod_probe._language_claimed_sources.discard(("movie", 5))
    assert seen == [("episode", 5)]  # the busy movie 5 must not block episode 5
