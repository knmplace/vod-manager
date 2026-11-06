# KNM: 2026-11-05 - one-time "re-validate language results" for installs that ran the
# older probe (no end-of-file read, no aliases, archive clicks that left feeds EN).
import json

import language_revalidate as rv


def _src(db, name, *, status=None, decision=None, label="EN", observed=None,
         probed=True, sibling=False, category=True):
    pid = db.upsert_provider(f"prov-{name}", "http://x.invalid", "u", "p")
    mid = db.upsert_movie(name, 2020)
    if category:
        db.place_movie_in_category(mid, db.upsert_category("Movies", "movie"))
    db.add_movie_source(mid, pid, f"s-{name}", "mp4")
    if sibling:
        other = db.upsert_provider(f"prov-{name}-en", "http://y.invalid", "u", "p")
        db.add_movie_source(mid, other, f"s-{name}-en", "mp4")
    conn = db._connect()
    try:
        sid = conn.execute("SELECT id FROM movie_sources WHERE provider_stream_id=?", (f"s-{name}",)).fetchone()["id"]
        conn.execute(
            """UPDATE movie_sources SET language=?, language_probe_status=?, language_probe_decision=?,
                      language_probe_languages=?, language_probed_at=? WHERE id=?""",
            (label, status, decision, json.dumps(observed) if observed is not None else None,
             "2026-11-01T00:00:00+00:00" if probed else None, sid))
        conn.commit()
    finally:
        conn.close()
    return sid, mid


def _row(db, sid):
    conn = db._connect()
    try:
        return dict(conn.execute("SELECT * FROM movie_sources WHERE id=?", (sid,)).fetchone())
    finally:
        conn.close()


def _movie(db, mid):
    conn = db._connect()
    try:
        return dict(conn.execute("SELECT * FROM movies WHERE id=?", (mid,)).fetchone())
    finally:
        conn.close()


def _targets(db):
    return {t["source_id"] for t in db.next_language_probe_targets(100, distinct_providers=False)}


def test_preview_counts_each_group_without_writing(db):
    _src(db, "unk", status="unknown", observed=[])
    _src(db, "obs", status="observed", observed=["FR"])
    _src(db, "auto", status="auto_approved", decision="approved", observed=["EN"])
    manual, _ = _src(db, "manual", status="manual_approved", decision="approved", observed=["EN"])
    _src(db, "failed-archive", status="observed", decision="approved", observed=["RU"], sibling=True)
    _src(db, "kept-en", status="observed", decision="approved", observed=["EN", "RU"])
    p = rv.preview()
    assert p["requeue"] == 2
    assert p["verify"] == 1
    assert p["repair_feeds"] == 1
    assert _row(db, manual)["language_probe_verify"] == 0


def test_apply_requeues_undecided_and_leaves_auto_approved(db):
    unk, _ = _src(db, "unk", status="unknown", observed=[])
    auto, _ = _src(db, "auto", status="auto_approved", decision="approved", observed=["EN"])
    rv.apply()
    assert _row(db, unk)["language_probed_at"] is None
    assert _row(db, auto)["language_probed_at"] is not None
    assert unk in _targets(db) and auto not in _targets(db)


def test_apply_queues_manual_confirmations_for_verify_keeping_decision(db):
    sid, _ = _src(db, "manual", status="manual_approved", decision="approved", observed=["EN"])
    rv.apply()
    row = _row(db, sid)
    assert row["language_probe_verify"] == 1
    assert row["language_probe_decision"] == "approved" and row["language"] == "EN"
    assert sid in _targets(db)
    assert rv.preview()["verify"] == 0  # one-time: not counted again


def test_verify_finding_confirmed_language_auto_approves(db):
    sid, _ = _src(db, "ok", status="manual_approved", decision="approved", observed=["EN"])
    rv.apply()
    assert db.apply_language_verify_result("movie", sid, ["EN"], "embedded_audio_tags") == "confirmed"
    row = _row(db, sid)
    assert row["language_probe_status"] == "auto_approved" and row["language_probe_verify"] == 0
    assert sid not in _targets(db)


def test_verify_still_unreadable_keeps_human_decision(db):
    sid, _ = _src(db, "unread", status="manual_approved", decision="approved", observed=["EN"])
    rv.apply()
    assert db.apply_language_verify_result("movie", sid, [], "embedded_audio_unreadable") == "kept"
    row = _row(db, sid)
    assert row["language_probe_status"] == "manual_approved"
    assert row["language_probe_decision"] == "approved" and row["language"] == "EN"
    assert row["language_probed_at"] is not None and row["language_probe_verify"] == 0
    assert sid not in _targets(db)


def test_verify_finding_only_unwanted_hides_that_feed_and_is_revertable(db):
    sid, mid = _src(db, "foreign", status="manual_approved", decision="approved", observed=["EN"], sibling=True)
    rv.apply()
    assert db.apply_language_verify_result("movie", sid, ["FR"], "embedded_audio_tags") == "hidden"
    assert _row(db, sid)["language"] == "FR"
    assert _movie(db, mid)["review_excluded"] == 0  # the other EN feed keeps the title live
    log = db.list_language_autoclean_log()
    assert log[0]["source_id"] == sid and log[0]["previous_language"] == "EN"
    assert db.revert_language_autoclean(log[0]["id"]) is True
    assert _row(db, sid)["language"] == "EN"


def test_verify_finding_other_wanted_language_relabels_and_stays_playable(db):
    sid, mid = _src(db, "multi", status="manual_approved", decision="approved", observed=["EN"])
    rv.apply()
    assert db.apply_language_verify_result("movie", sid, ["MULTI", "FR"], "embedded_audio_tags") == "relabelled"
    assert _row(db, sid)["language"] == "MULTI"
    assert _movie(db, mid)["review_excluded"] == 0


def test_apply_repairs_failed_archive_clicks(db):
    sid, mid = _src(db, "failed", status="observed", decision="approved", observed=["RU"], sibling=True)
    keep, _ = _src(db, "kept", status="observed", decision="approved", observed=["EN", "RU"])
    result = rv.apply()
    assert result["repaired_feeds"] == 1
    assert _row(db, sid)["language"] == "RU"
    assert _row(db, keep)["language"] == "EN"
    assert _movie(db, mid)["review_excluded"] == 0
    assert db.list_language_autoclean_log()[0]["source_id"] == sid


def test_apply_restores_language_hidden_title_with_wanted_feed_but_not_import_policy(db):
    _, wrong = _src(db, "wrongly-hidden", status="auto_approved", decision="approved", observed=["EN"])
    _, policy = _src(db, "policy-hidden", status="auto_approved", decision="approved", observed=["EN"])
    conn = db._connect()
    conn.execute("UPDATE movies SET review_excluded=1, review_excluded_language=1 WHERE id=?", (wrong,))
    conn.execute("UPDATE movies SET review_excluded=1, review_excluded_language=1, review_excluded_import_policy=1 WHERE id=?", (policy,))
    conn.commit()
    conn.close()
    assert rv.preview()["restore_titles"] == 1
    rv.apply()
    assert _movie(db, wrong)["review_excluded"] == 0
    assert _movie(db, policy)["review_excluded"] == 1


def test_second_run_has_nothing_left_to_do(db):
    _src(db, "unk", status="unknown", observed=[])
    _src(db, "manual", status="manual_approved", decision="approved", observed=["EN"])
    _src(db, "failed", status="observed", decision="approved", observed=["RU"], sibling=True)
    rv.apply()
    p = rv.preview()
    assert (p["requeue"], p["verify"], p["repair_feeds"], p["restore_titles"]) == (0, 0, 0, 0)


def test_rows_already_handled_by_the_new_probe_are_not_queued_again(db):
    unk, _ = _src(db, "unk", status="unknown", observed=[])
    manual, _ = _src(db, "manual", status="manual_approved", decision="approved", observed=["EN"])
    rv.apply()
    db.set_source_language_probe("movie", unk, [], "unknown", "embedded_audio_unreadable")
    db.apply_language_verify_result("movie", manual, [], "embedded_audio_unreadable")
    p = rv.preview()
    assert (p["requeue"], p["verify"]) == (0, 0) and p["applied_at"]
    assert rv.apply()["requeued"] == 0


def test_probe_runs_verify_branch_without_raising_a_mismatch(db, monkeypatch):
    import asyncio
    import vod_probe
    sid, _ = _src(db, "probe", status="manual_approved", decision="approved", observed=["EN"], sibling=True)
    rv.apply()

    async def fake_remote(*a, **k):
        return ["FR"]
    monkeypatch.setattr(vod_probe, "_probe_remote_language", fake_remote)
    monkeypatch.setattr(vod_probe.shutil, "which", lambda name: "/usr/bin/ffprobe")
    out = asyncio.run(vod_probe.probe_language_source("movie", sid))
    assert out["mismatch"] is False and out["verify"] == "hidden"
    assert _row(db, sid)["language"] == "FR"


def test_routes_preview_then_apply(db):
    import asyncio
    import vod_routes
    _src(db, "unk", status="unknown", observed=[])
    assert asyncio.run(vod_routes.language_revalidate_preview())["requeue"] == 1
    assert asyncio.run(vod_routes.language_revalidate_apply())["requeued"] == 1
    assert asyncio.run(vod_routes.language_revalidate_preview())["requeue"] == 0
