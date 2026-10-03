def test_possible_matches_can_be_reviewed_and_approved_in_bulk(db):
    provider_id = db.upsert_provider("Provider", "http://provider.invalid", "u", "p", provider_type="xc")
    now = db._now()
    conn = db._connect()
    conn.execute("INSERT INTO movies (name, year, tmdb_id, created_at) VALUES (?, ?, ?, ?)", ("Jeffrey", 1995, "123", now))
    candidate_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute("INSERT INTO movies (name, year, tmdb_id, needs_year_review, created_at) VALUES (?, ?, ?, ?, ?)", ("Jeffrey", None, None, 1, now))
    item_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute("INSERT INTO movie_sources (movie_id, provider_id, provider_stream_id, raw_name, language, added_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (candidate_id, provider_id, "candidate", "Jeffrey", "EN", now, now))
    conn.execute("INSERT INTO movie_sources (movie_id, provider_id, provider_stream_id, raw_name, language, added_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (item_id, provider_id, "item", "Jeffrey", "EN", now, now))
    conn.commit()
    conn.close()

    page = db.list_possible_metadata_matches("movie")
    assert page["total"] == 1
    assert page["items"][0]["id"] == item_id
    assert page["items"][0]["candidates"][0]["id"] == candidate_id

    result = db.bulk_merge_possible_metadata_matches("movie", [{"item_id": item_id, "candidate_id": candidate_id}])
    assert result == {"merged": 1, "skipped": []}
    assert db.get_movie(item_id) is None
    assert db.get_movie(candidate_id)["year"] == 1995
