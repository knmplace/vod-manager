# KNM: 2026-10-14 -- flagged (needs_year_review=1) movies with a TMDB id and a
# TMDB release date stayed yearless, so they were held out of every category
# and hidden from Metadata Review, while the toolbar button still counted them.


def _movie(db, name="Flashback", tmdb_id="123", flagged=1, year=None, enriched=False, release_date=None, adult=0):
    conn = db._connect()
    cur = conn.execute(
        "INSERT INTO movies (name, year, tmdb_id, needs_year_review, release_date, last_enriched_at, is_adult, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (name, year, tmdb_id, flagged, release_date, db._now() if enriched else None, adult, db._now()),
    )
    conn.commit()
    conn.close()
    return cur.lastrowid


def _row(db, movie_id):
    return db.get_movie(movie_id)


def test_enrichment_sets_year_from_release_date_and_clears_flag(db):
    mid = _movie(db)
    db.apply_movie_enrichment_batch([{"movie_id": mid, "fields": {"release_date": "1990-02-02"}}])
    row = _row(db, mid)
    assert row["year"] == 1990
    assert row["needs_year_review"] == 0


def test_enrichment_without_release_date_keeps_flag(db):
    mid = _movie(db)
    db.apply_movie_enrichment_batch([{"movie_id": mid, "fields": {"release_date": None}}])
    row = _row(db, mid)
    assert row["year"] is None
    assert row["needs_year_review"] == 1


def test_enrichment_leaves_unflagged_or_dated_movies_alone(db):
    unflagged = _movie(db, name="A", flagged=0)
    dated = _movie(db, name="B", year=2001)
    db.apply_movie_enrichment_batch([
        {"movie_id": unflagged, "fields": {"release_date": "1990-02-02"}},
        {"movie_id": dated, "fields": {"release_date": "1990-02-02"}},
    ])
    assert _row(db, unflagged)["year"] is None
    assert _row(db, dated)["year"] == 2001
    assert _row(db, dated)["needs_year_review"] == 1


def test_startup_heals_already_enriched_stuck_movies(db):
    stuck = _movie(db, enriched=True, release_date="1990-02-02")
    blank = _movie(db, name="Blank", enriched=True, release_date="")
    db.init_db()
    assert _row(db, stuck)["year"] == 1990
    assert _row(db, stuck)["needs_year_review"] == 0
    assert _row(db, blank)["needs_year_review"] == 1


# KNM: 2026-10-15 -- archived (rule-excluded) movies also take the TMDB year,
# so they look right under "Show archived" and come back fixed if restored.
def test_startup_heals_archived_stuck_movies(db):
    mid = _movie(db, enriched=True, release_date="2019-10-02")
    conn = db._connect()
    conn.execute("UPDATE movies SET review_excluded=1 WHERE id=?", (mid,))
    conn.commit()
    conn.close()
    db.init_db()
    row = _row(db, mid)
    assert row["year"] == 2019
    assert row["needs_year_review"] == 0
    assert row["review_excluded"] == 1


def test_review_lists_enriched_tmdb_backed_rows_still_missing_a_year(db):
    _movie(db, name="Pending", enriched=False)
    _movie(db, name="Yearless", enriched=True)
    names = {r["name"] for r in db.list_metadata_review("movie")["movies"]}
    assert "Yearless" in names
    assert "Pending" not in names


def test_review_lists_enriched_series_without_a_year(db):
    conn = db._connect()
    conn.execute(
        "INSERT INTO series (name, tmdb_id, needs_year_review, tmdb_metadata_enriched_at, created_at) VALUES (?,?,?,?,?)",
        ("The Last Word", "33265", 1, db._now(), db._now()),
    )
    conn.commit()
    conn.close()
    assert [r["name"] for r in db.list_metadata_review("series")["series"]] == ["The Last Word"]


def test_review_counts_match_the_review_list(db):
    _movie(db, name="Yearless", enriched=True)
    _movie(db, name="Adult", tmdb_id=None, flagged=0, adult=1)
    _movie(db, name="Pending", enriched=False)
    counts = db.count_metadata_review()
    assert counts == {"movies": {"total": 2, "adult": 1}, "series": {"total": 0, "adult": 0}}
