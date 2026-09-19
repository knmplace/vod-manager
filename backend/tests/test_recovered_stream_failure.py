def test_successful_successor_clears_recent_stream_failure(db):
    provider_id = db.upsert_provider(
        "provider-a", "http://provider-a.example", "user", "pass",
    )
    movie_id = db.upsert_movie("Example Movie", 2024)
    db.add_movie_source(movie_id, provider_id, "movie-1")
    db.log_stream_failure(
        "movie", "Example Movie", "relay-user", [{"provider": "provider-a"}],
        "RemoteProtocolError", movie_id=movie_id, client_ip="192.0.2.10",
    )

    cleared = db.clear_recovered_stream_failures(
        "movie", "Example Movie", "relay-user", movie_id=movie_id,
        client_ip="192.0.2.10",
    )

    assert cleared == 1
    assert db.list_stream_failures() == []
