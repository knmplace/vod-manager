import asyncio

import config
import vod_db
import vod_importer
import vod_routes


def _provider(db, provider_type: str) -> int:
    return db.upsert_provider(
        f"{provider_type}-provider",
        f"http://{provider_type}.invalid",
        "user",
        "pass",
        provider_type=provider_type,
    )


def _movie_source(db, movie_id: int, provider_id: int, stream_id: str, raw_name: str, language: str):
    conn = db._connect()
    conn.execute(
        "INSERT INTO movie_sources "
        "(movie_id, provider_id, provider_stream_id, raw_name, language, added_at, last_seen_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (movie_id, provider_id, stream_id, raw_name, language, "1", "1"),
    )
    conn.commit()
    conn.close()


def _series_source(db, series_id: int, provider_id: int, source_id: str, raw_name: str, language: str):
    conn = db._connect()
    conn.execute(
        "INSERT INTO series_sources "
        "(series_id, provider_id, provider_series_id, raw_name, language, added_at, last_seen_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (series_id, provider_id, source_id, raw_name, language, "1", "1"),
    )
    conn.commit()
    conn.close()


def _archive_state(db, content_type: str, item_id: int) -> dict:
    table = "movies" if content_type == "movie" else "series"
    conn = db._connect()
    row = conn.execute(
        f"SELECT review_excluded, review_excluded_manual, review_excluded_language, "
        f"review_excluded_import_policy FROM {table} WHERE id=?",
        (item_id,),
    ).fetchone()
    conn.close()
    return dict(row)


def test_preview_reports_sources_cards_samples_and_provider_types_without_writing(db):
    providers = {kind: _provider(db, kind) for kind in ("xc", "plex", "emby", "jellyfin", "library")}
    es_only = db.upsert_movie("Spanish only", 2020)
    _movie_source(db, es_only, providers["xc"], "xc-es", "ES - Spanish only", "ES")

    mixed = db.upsert_movie("Mixed sources", 2021)
    _movie_source(db, mixed, providers["plex"], "plex-es", "ES - Mixed sources", "ES")
    _movie_source(db, mixed, providers["library"], "library-en", "EN - Mixed sources", "EN")

    non_latin = db.upsert_movie("Arabic source", 2022)
    _movie_source(db, non_latin, providers["emby"], "emby-ar", "فيلم عربي", "AR")

    country = db.upsert_series("Country edition", 2023)
    _series_source(db, country, providers["jellyfin"], "jf-pl", "Country edition (PL)", "PL")

    report = db.apply_import_exclusion_policy(["ES"], True, ["PL"], dry_run=True)

    assert report["dry_run"] is True
    assert report["sources"]["total"] == 5
    assert report["sources"]["excluded"] == 4
    assert report["sources"]["allowed"] == 1
    assert set(report["sources"]["provider_types"]) == {"xc", "plex", "emby", "jellyfin", "library"}
    assert report["movies"]["cards_archived"] == 2
    assert report["series"]["cards_archived"] == 1
    assert report["movies"]["cards_all_sources_excluded"] == 2
    assert any(sample["name"] == "Spanish only" for sample in report["movies"]["archive_samples"])
    assert _archive_state(db, "movie", es_only)["review_excluded"] == 0
    assert _archive_state(db, "movie", mixed)["review_excluded"] == 0


def test_apply_preserves_sources_manual_archives_and_restores_only_its_owner(db):
    provider_id = _provider(db, "xc")
    policy_movie = db.upsert_movie("Policy movie", 2020)
    _movie_source(db, policy_movie, provider_id, "es-1", "ES - Policy movie", "ES")
    manual_movie = db.upsert_movie("Manual movie", 2021)
    _movie_source(db, manual_movie, provider_id, "es-2", "ES - Manual movie", "ES")
    db.bulk_set_review_excluded("movie", [manual_movie], True)

    conn = db._connect()
    conn.execute(
        "INSERT INTO tmdb_auto_match (content_type,item_id,status,reason,attempted_at) VALUES ('movie',?,'ambiguous','test','1')",
        (policy_movie,),
    )
    conn.commit()
    conn.close()

    applied = db.apply_import_exclusion_policy(["ES"], False, [], dry_run=False)

    assert applied["movies"]["cards_archived"] == 1
    assert applied["movies"]["manual_cards_unchanged"] == 1
    assert _archive_state(db, "movie", policy_movie) == {
        "review_excluded": 1,
        "review_excluded_manual": 0,
        "review_excluded_language": 0,
        "review_excluded_import_policy": 1,
    }
    assert _archive_state(db, "movie", manual_movie)["review_excluded_import_policy"] == 0
    conn = db._connect()
    assert conn.execute("SELECT COUNT(*) FROM movie_sources").fetchone()[0] == 2
    assert conn.execute(
        "SELECT COUNT(*) FROM tmdb_auto_match WHERE content_type='movie' AND item_id=?", (policy_movie,)
    ).fetchone()[0] == 0
    conn.close()

    restored = db.apply_import_exclusion_policy([], False, [], dry_run=False)
    assert restored["movies"]["cards_restored"] == 1
    assert _archive_state(db, "movie", policy_movie)["review_excluded"] == 0
    assert _archive_state(db, "movie", manual_movie)["review_excluded"] == 1


def test_import_and_playback_archive_owners_release_independently(db):
    provider_id = _provider(db, "xc")
    movie_id = db.upsert_movie("Spanish movie", 2020)
    _movie_source(db, movie_id, provider_id, "es", "ES - Spanish movie", "ES")

    assert db.archive_disabled_language_content(enabled_languages={"EN"})["movies_archived"] == 1
    db.apply_import_exclusion_policy(["ES"], False, [], dry_run=False)
    assert _archive_state(db, "movie", movie_id) == {
        "review_excluded": 1,
        "review_excluded_manual": 0,
        "review_excluded_language": 1,
        "review_excluded_import_policy": 1,
    }

    playback_release = db.archive_disabled_language_content(enabled_languages={"EN", "ES"})
    assert playback_release["movies_unarchived"] == 0
    assert _archive_state(db, "movie", movie_id)["review_excluded"] == 1
    assert _archive_state(db, "movie", movie_id)["review_excluded_language"] == 0

    policy_release = db.apply_import_exclusion_policy([], False, [], dry_run=False)
    assert policy_release["movies"]["cards_restored"] == 1
    assert _archive_state(db, "movie", movie_id)["review_excluded"] == 0


def test_preview_and_apply_routes_use_saved_policy_and_resweep(db, monkeypatch):
    provider_id = _provider(db, "xc")
    movie_id = db.upsert_movie("Spanish movie", 2020)
    _movie_source(db, movie_id, provider_id, "es", "ES - Spanish movie", "ES")
    config.save_import_language_exclusion(["ES"], False)
    config.save_import_country_exclusion([])
    resweeps = []

    async def fake_resweep():
        resweeps.append(True)

    monkeypatch.setattr(vod_importer, "resweep_smart_categories", fake_resweep)
    preview = asyncio.run(vod_routes.preview_import_exclusions())
    assert preview["dry_run"] is True
    assert _archive_state(db, "movie", movie_id)["review_excluded"] == 0

    applied = asyncio.run(vod_routes.apply_import_exclusions(
        vod_routes.ImportExclusionsApplyRequest(preview_token=preview["preview_token"])
    ))
    assert applied["dry_run"] is False
    assert resweeps == [True]
    assert _archive_state(db, "movie", movie_id)["review_excluded"] == 1


def test_apply_route_rejects_stale_policy_preview(db):
    config.save_import_language_exclusion(["ES"], False)
    preview = asyncio.run(vod_routes.preview_import_exclusions())
    config.save_import_language_exclusion(["ES", "DE"], False)

    try:
        asyncio.run(vod_routes.apply_import_exclusions(
            vod_routes.ImportExclusionsApplyRequest(preview_token=preview["preview_token"])
        ))
        assert False, "expected stale preview to be rejected"
    except vod_routes.HTTPException as exc:
        assert exc.status_code == 409


def test_reapply_reports_cards_already_archived(db):
    provider_id = _provider(db, "xc")
    policy_movie = db.upsert_movie("Policy movie", 2020)
    _movie_source(db, policy_movie, provider_id, "es-1", "ES - Policy movie", "ES")
    manual_movie = db.upsert_movie("Manual movie", 2021)
    _movie_source(db, manual_movie, provider_id, "es-2", "ES - Manual movie", "ES")
    db.bulk_set_review_excluded("movie", [manual_movie], True)
    allowed_movie = db.upsert_movie("Allowed movie", 2022)
    _movie_source(db, allowed_movie, provider_id, "en-1", "EN - Allowed movie", "EN")

    first = db.apply_import_exclusion_policy(["ES"], False, [], dry_run=False)
    assert first["movies"]["cards_archived"] == 1
    assert first["movies"]["cards_already_archived"] == 1  # the manual one

    again = db.apply_import_exclusion_policy(["ES"], False, [], dry_run=False)
    assert again["movies"]["cards_archived"] == 0
    assert again["movies"]["cards_restored"] == 0
    assert again["movies"]["cards_already_archived"] == 2


def _source_names(db, table: str, fk: str, card_id: int) -> list[str]:
    conn = db._connect()
    rows = conn.execute(f"SELECT raw_name FROM {table} WHERE {fk}=? ORDER BY raw_name", (card_id,)).fetchall()
    conn.close()
    return [row["raw_name"] for row in rows]


def test_apply_removes_excluded_sources_from_mixed_cards(db):
    # KNM: 2026-10-27 -- a card with a clean source stayed live with its
    # excluded-country source still attached (served/streamed).
    clean = _provider(db, "xc")
    tagged = db.upsert_provider("tagged", "http://tagged.invalid", "u", "p")
    series_id = db.upsert_series("30 Coins", 2020)
    _series_source(db, series_id, clean, "58005", "30 Coins (2020)", "EN")
    _series_source(db, series_id, tagged, "3887", "EN - 30 Coins (ES)", "EN")
    movie_id = db.upsert_movie("Mixed movie", 2021)
    _movie_source(db, movie_id, clean, "en", "Mixed movie", "EN")
    _movie_source(db, movie_id, tagged, "es", "ES - Mixed movie", "ES")

    preview = db.apply_import_exclusion_policy(["ES"], False, ["ES"], dry_run=True)
    assert preview["series"]["sources_removed"] == 1
    assert preview["movies"]["sources_removed"] == 1
    assert len(_source_names(db, "series_sources", "series_id", series_id)) == 2

    applied = db.apply_import_exclusion_policy(["ES"], False, ["ES"], dry_run=False)
    assert applied["series"]["sources_removed"] == 1
    assert _source_names(db, "series_sources", "series_id", series_id) == ["30 Coins (2020)"]
    assert _source_names(db, "movie_sources", "movie_id", movie_id) == ["Mixed movie"]
    assert _archive_state(db, "series", series_id)["review_excluded"] == 0
    assert _archive_state(db, "movie", movie_id)["review_excluded"] == 0


def test_apply_leaves_manual_archive_card_sources_alone(db):
    provider_id = _provider(db, "xc")
    movie_id = db.upsert_movie("Manual mixed", 2021)
    _movie_source(db, movie_id, provider_id, "en", "Manual mixed", "EN")
    _movie_source(db, movie_id, provider_id, "es", "ES - Manual mixed", "ES")
    db.bulk_set_review_excluded("movie", [movie_id], True)

    applied = db.apply_import_exclusion_policy(["ES"], False, [], dry_run=False)
    assert applied["movies"]["sources_removed"] == 0
    assert len(_source_names(db, "movie_sources", "movie_id", movie_id)) == 2


def test_saving_exclusion_lists_applies_policy_and_resweeps(db, monkeypatch):
    # KNM: 2026-10-27 -- an exclusion saved after content was already stored
    # stayed live until someone ran preview/apply by hand.
    provider_id = _provider(db, "xc")
    movie_id = db.upsert_movie("Spanish movie", 2020)
    _movie_source(db, movie_id, provider_id, "es", "Spanish movie (ES)", "EN")
    resweeps = []

    async def fake_resweep():
        resweeps.append(True)

    monkeypatch.setattr(vod_importer, "resweep_smart_categories", fake_resweep)
    asyncio.run(vod_routes.save_import_country_exclusion_settings(
        vod_routes.ImportCountryExclusionRequest(exclude_country_codes=["ES"])
    ))
    assert _archive_state(db, "movie", movie_id)["review_excluded_import_policy"] == 1

    asyncio.run(vod_routes.save_import_country_exclusion_settings(
        vod_routes.ImportCountryExclusionRequest(exclude_country_codes=[])
    ))
    assert _archive_state(db, "movie", movie_id)["review_excluded"] == 0

    asyncio.run(vod_routes.save_import_language_exclusion_settings(
        vod_routes.ImportLanguageExclusionRequest(exclude_prefixes=["EN"], exclude_non_latin=False)
    ))
    assert _archive_state(db, "movie", movie_id)["review_excluded_import_policy"] == 1
    assert resweeps == [True, True, True]


def _set_import_pointer(db, series_id: int, provider_id: int, source_id: str):
    conn = db._connect()
    conn.execute(
        "UPDATE series SET import_provider_id=?, import_provider_series_id=? WHERE id=?",
        (provider_id, source_id, series_id),
    )
    conn.commit()
    conn.close()


def _series_source_ids(db, series_id: int) -> set:
    conn = db._connect()
    rows = conn.execute(
        "SELECT provider_id, provider_series_id FROM series_sources WHERE series_id=?", (series_id,),
    ).fetchall()
    conn.close()
    return {(row["provider_id"], row["provider_series_id"]) for row in rows}


def test_backfill_does_not_resurrect_a_removed_source_onto_a_card_that_has_sources(db):
    xc = _provider(db, "xc")
    library = _provider(db, "library")
    holder = db.upsert_series("Holder", 2020)
    _series_source(db, holder, xc, "shared-es", "ES - Holder", "ES")
    _series_source(db, holder, library, "holder-en", "EN - Holder", "EN")
    stale = db.upsert_series("Stale pointer", 2021)
    _series_source(db, stale, library, "stale-en", "EN - Stale pointer", "EN")
    _set_import_pointer(db, stale, xc, "shared-es")

    db.apply_import_exclusion_policy(["ES"], False, [], dry_run=False)
    db.backfill_series_sources()

    assert _series_source_ids(db, stale) == {(library, "stale-en")}


def test_backfill_still_creates_a_source_for_a_card_with_none(db):
    xc = _provider(db, "xc")
    legacy = db.upsert_series("Legacy only", 2020)
    _set_import_pointer(db, legacy, xc, "legacy-1")

    db.backfill_series_sources()

    assert _series_source_ids(db, legacy) == {(xc, "legacy-1")}


def _set_policy_archived(db, table: str, item_id: int):
    conn = db._connect()
    conn.execute(
        f"UPDATE {table} SET review_excluded=1, review_excluded_import_policy=1 WHERE id=?", (item_id,),
    )
    conn.commit()
    conn.close()


def test_sync_unarchive_also_clears_the_import_policy_owner(db):
    xc = _provider(db, "xc")
    series_item = {"name": "Synced show", "year": 2020, "provider_series_id": "s1",
                   "raw_name": "EN - Synced show", "_has_detail": True}
    movie_item = {"name": "Synced movie", "year": 2020, "provider_stream_id": "m1",
                  "container_extension": "mp4", "raw_name": "EN - Synced movie", "_has_detail": True}
    db.bulk_import_series(xc, [dict(series_item)])
    db.bulk_import_movies(xc, [dict(movie_item)])
    series_id = db.get_series_by_name_year("Synced show", 2020)["id"]
    movie_id = db.get_movie_by_name_year("Synced movie", 2020)["id"]
    _set_policy_archived(db, "series", series_id)
    _set_policy_archived(db, "movies", movie_id)

    db.bulk_import_series(xc, [dict(series_item)])
    db.bulk_import_movies(xc, [dict(movie_item)])

    for content_type, item_id in (("series", series_id), ("movie", movie_id)):
        state = _archive_state(db, content_type, item_id)
        assert (state["review_excluded"], state["review_excluded_import_policy"]) == (0, 0), content_type
