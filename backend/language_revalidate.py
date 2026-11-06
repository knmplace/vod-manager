"""One-time "Re-validate language results" for installs that ran the older probe.

KNM: 2026-11-05 - the older probe missed tracks in end-indexed MP4s and had no
code aliases, and older archive clicks left unwanted feeds labelled EN (still
served). This puts those results back through the current probe:
  requeue  - undecided unknown/observed/error rows are probed again;
  verify   - a person's earlier confirmation is re-checked once, keeping the
             decision unless the probe now reads only unwanted audio;
  repair   - approved feeds whose probe found only unwanted audio but still carry
             a wanted label are hidden (logged, revertable like auto-clean);
  restore  - language-hidden titles that do have a wanted feed come back
             (never import-policy or manual hides).
Rows decided by matching tags (auto_approved) are left alone. Rows probed after
the first run already used the current probe, so a second run finds nothing.
"""
import datetime
import json

import config
import vod_db

_TABLES = (("movie", "movie_sources"), ("episode", "episode_sources"))


def _cutoff() -> str:
    return config.get_language_revalidate_applied_at() or \
        datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


_REQUEUE = """language_probe_status IN ('unknown','observed','error') AND language_probe_decision IS NULL
              AND language_probed_at IS NOT NULL AND language_probed_at < ?"""
_TAGLESS = """language_probe_status IN ('unknown','observed')
              AND COALESCE(language_probe_languages,'[]') IN ('[]','["UNKNOWN"]')"""
_VERIFY = """language_probe_status='manual_approved' AND language_probe_verify=0
             AND language_probed_at IS NOT NULL AND language_probed_at < ?"""


def _repair_rows(conn) -> list[tuple[str, int, str | None, list[str]]]:
    wanted = {vod_db.canonical_language(e) for e in vod_db.get_enabled_languages()} | {"MULTI"}
    out = []
    for kind, table in _TABLES:
        for row in conn.execute(f"""SELECT id, language, language_probe_languages FROM {table}
                                    WHERE language_probe_decision='approved' AND language_probe_status='observed'
                                      AND language_probe_languages IS NOT NULL"""):
            try:
                usable = [o for o in json.loads(row["language_probe_languages"] or "[]") if o and o != "UNKNOWN"]
            except (TypeError, ValueError):
                continue
            if not usable or {vod_db.canonical_language(o) for o in usable} & wanted:
                continue
            if vod_db.canonical_language(row["language"] or "EN") in wanted:
                out.append((kind, row["id"], row["language"], sorted(usable)))
    return out


def _hidden_ids(conn) -> tuple[set[int], set[int]]:
    q = "SELECT id FROM {} WHERE review_excluded_language=1 AND review_excluded_manual=0"
    return ({r[0] for r in conn.execute(q.format("movies"))}, {r[0] for r in conn.execute(q.format("series"))})


def preview() -> dict:
    cutoff = _cutoff()
    conn = vod_db._connect()
    try:
        requeue = sum(conn.execute(f"SELECT COUNT(*) FROM {t} WHERE {_REQUEUE}", (cutoff,)).fetchone()[0] for _, t in _TABLES)
        verify = sum(conn.execute(f"SELECT COUNT(*) FROM {t} WHERE {_VERIFY}", (cutoff,)).fetchone()[0] for _, t in _TABLES)
        repair = _repair_rows(conn)
        movie_ids, series_ids = _hidden_ids(conn)
    finally:
        conn.close()
    restore = vod_db.archive_disabled_language_content(movie_ids, series_ids, dry_run=True)
    return {"requeue": requeue, "verify": verify, "repair_feeds": len(repair),
            "restore_titles": restore["movies_unarchived"] + restore["series_unarchived"],
            "applied_at": config.get_language_revalidate_applied_at()}


def apply() -> dict:
    cutoff = _cutoff()
    config.save_language_revalidate_applied_at(cutoff)
    conn = vod_db._connect()
    try:
        repair = _repair_rows(conn)
    finally:
        conn.close()
    repaired = 0
    for kind, sid, previous, observed in repair:
        try:
            result = vod_db.decide_language_mismatch(kind, sid, "approved")
        except ValueError:
            continue
        vod_db.log_language_autoclean(kind, sid, previous, result.get("language"), observed, None)
        repaired += 1
    conn = vod_db._connect()
    try:
        movie_ids, series_ids = _hidden_ids(conn)
    finally:
        conn.close()
    restore = vod_db.archive_disabled_language_content(movie_ids, series_ids)
    requeued = verified = 0
    with vod_db._WRITE_LOCK:
        conn = vod_db._connect()
        try:
            for _, t in _TABLES:
                verified += conn.execute(
                    f"UPDATE {t} SET language_probe_verify=1, language_probed_at=NULL WHERE {_VERIFY}", (cutoff,)).rowcount
                # KNM: 2026-11-05 - also drop a tag-less old-probe result, so a queued row reads as
                # not-yet-checked and Unknown review lists only results from the current probe.
                tagless = f"CASE WHEN {_TAGLESS} THEN NULL ELSE {{col}} END"
                requeued += conn.execute(f"""UPDATE {t} SET language_probed_at=NULL,
                    language_probe_status={tagless.format(col='language_probe_status')},
                    language_probe_languages={tagless.format(col='language_probe_languages')},
                    language_probe_confidence={tagless.format(col='language_probe_confidence')},
                    language_probe_method={tagless.format(col='language_probe_method')}
                    WHERE {_REQUEUE}""", (cutoff,)).rowcount
            vod_db._commit_with_retry(conn)
        finally:
            conn.close()
    return {"requeued": requeued, "verify_queued": verified, "repaired_feeds": repaired,
            "restored_titles": restore["movies_unarchived"] + restore["series_unarchived"], "applied_at": cutoff}
