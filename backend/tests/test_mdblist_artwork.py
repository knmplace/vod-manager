import pytest
import asyncio

import config
import mdblist_artwork
import mdblist_sync
import vod_routes


def test_artwork_search_is_disabled_until_opted_in_and_tier_selected(db):
    assert config.get_mdblist_artwork_settings()["enabled"] is False
    with pytest.raises(ValueError, match="tier"):
        config.save_mdblist_artwork_settings(True, None)

    config.save_mdblist_api_key("test-key")
    config.save_mdblist_artwork_settings(True, "free")
    assert config.get_mdblist_artwork_settings()["daily_limit"] == 1_000


def test_artwork_quota_uses_selected_tier_and_server_remaining_headers(db):
    config.save_mdblist_api_key("test-key")
    config.save_mdblist_artwork_settings(True, "free")
    config.record_mdblist_artwork_rate_headers({
        "X-RateLimit-Limit": "1000",
        "X-RateLimit-Remaining": "2",
        "X-RateLimit-Reset": "9999999999",
    })
    assert config.get_mdblist_artwork_usage()["remaining_today"] == 2
    config.reserve_mdblist_artwork_request()
    assert config.get_mdblist_artwork_usage()["remaining_today"] == 1
    config.reserve_mdblist_artwork_request()
    with pytest.raises(ValueError, match="daily limit"):
        config.reserve_mdblist_artwork_request()


def test_candidate_marks_identity_conflicts_without_hiding_poster():
    candidate = mdblist_artwork._candidate(
        {
            "title": "Streets",
            "year": 2016,
            "ids": {"tmdb": 444},
            "poster": "https://image.tmdb.org/t/p/w500/poster.jpg",
        },
        expected_title="Streets",
        expected_year=2016,
        requested_tmdb_id="444",
    )
    assert candidate["identity_match"] is True
    assert candidate["poster_url"].startswith("https://")

    conflict = mdblist_artwork._candidate(
        {
            "title": "Different title",
            "year": 2016,
            "ids": {"tmdb": 444},
            "poster": "https://image.tmdb.org/t/p/w500/poster.jpg",
        },
        expected_title="Streets",
        expected_year=2016,
        requested_tmdb_id="444",
    )
    assert conflict["poster_url"]
    assert conflict["identity_match"] is False


def test_lookup_by_tmdb_id_calls_dedicated_mdb_endpoint_and_reserves_quota(db, monkeypatch):
    config.save_mdblist_api_key("test-key")
    config.save_mdblist_artwork_settings(True, "free")
    calls = []

    class Response:
        status_code = 200
        headers = {
            "X-RateLimit-Limit": "1000",
            "X-RateLimit-Remaining": "999",
            "X-RateLimit-Reset": "9999999999",
        }

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "title": "Streets",
                "year": 2016,
                "ids": {"tmdb": 444},
                "poster": "https://image.tmdb.org/t/p/w500/poster.jpg",
            }

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params=None):
            calls.append((url, params))
            return Response()

    monkeypatch.setattr(mdblist_artwork.httpx, "AsyncClient", Client)
    matches = asyncio.run(mdblist_artwork.lookup_by_tmdb_id("movie", "444", "Streets", 2016))
    assert calls[0][0].endswith("/tmdb/movie/444/")
    assert calls[0][1]["apikey"] == "test-key"
    assert matches[0]["identity_match"] is True
    assert config.get_mdblist_artwork_usage()["requests_today"] == 1
    assert config.get_mdblist_artwork_usage()["remaining_today"] == 999


def test_adult_titles_are_rejected_by_all_artwork_search_paths(db):
    adult_id = db.upsert_movie("Adult title", 2020)
    conn = db._connect()
    conn.execute("UPDATE movies SET is_adult=1 WHERE id=?", (adult_id,))
    conn.commit()
    conn.close()

    with pytest.raises(vod_routes.HTTPException) as exc:
        vod_routes._missing_artwork_search_item("movie", adult_id)
    assert exc.value.status_code == 403


def test_public_list_rate_headers_feed_shared_account_quota(db):
    config.save_mdblist_api_key("test-key")
    config.save_mdblist_artwork_settings(True, "supporter_3")
    config.record_mdblist_artwork_rate_headers({
        "X-RateLimit-Limit": "1000",
        "X-RateLimit-Remaining": "0",
        "X-RateLimit-Reset": "9999999999",
    })
    assert config.get_mdblist_artwork_usage()["remaining_today"] == 0


def test_public_list_sync_reports_account_rate_headers(monkeypatch):
    recorded = []

    class Response:
        headers = {
            "X-Has-More": "false",
            "X-RateLimit-Limit": "1000",
            "X-RateLimit-Remaining": "900",
        }

        def raise_for_status(self):
            pass

        def json(self):
            return {"movies": [], "shows": []}

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(mdblist_sync.httpx, "AsyncClient", Client)
    monkeypatch.setattr(mdblist_sync.config, "record_mdblist_artwork_rate_headers", recorded.append)
    asyncio.run(mdblist_sync.fetch_list_items("test-key", "123"))
    assert recorded == [Response.headers]
