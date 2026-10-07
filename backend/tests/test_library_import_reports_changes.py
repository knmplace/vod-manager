"""Plex/Emby/Jellyfin/library imports must report which cards they created or
changed. Sync History counts changes from these ids, so without them a Plex
run that added new episodes showed "0 changes"."""

import asyncio

import emby_vod_client
import emby_vod_importer
import plex_client
import plex_importer


def _show(eps, **extra):
    return {
        "name": "Example Show", "year": 2020, "provider_series_id": "show-1",
        "genre": "Drama", "last_enriched_at": "1",
        "episodes": [{"season_number": 1, "episode_number": n, "name": f"Ep {n}",
                      "provider_stream_id": f"ep-{n}", "container_extension": "mkv"} for n in eps],
        **extra,
    }


def _movie(stream="m-1", **extra):
    return {"name": "Example Movie", "year": 2020, "provider_stream_id": stream,
            "container_extension": "mkv", "genre": "Drama", "last_enriched_at": "1", **extra}


def test_series_first_import_reports_created(db):
    pid = db.upsert_provider("Plex", "http://plex.invalid", "u", "p")
    r = db.bulk_import_plex_series(pid, [_show([1])])
    assert len(r["created_series_ids"]) == 1
    assert r["changed_series_ids"] == r["created_series_ids"]


def test_series_unchanged_reimport_reports_nothing(db):
    pid = db.upsert_provider("Plex", "http://plex.invalid", "u", "p")
    db.bulk_import_plex_series(pid, [_show([1, 2])])
    # last_enriched_at is stamped fresh on every pass; that alone is no change.
    r = db.bulk_import_plex_series(pid, [_show([1, 2], last_enriched_at="2")])
    assert r["changed_series_ids"] == []
    assert r["created_series_ids"] == []
    assert r["episodes_added"] == 0


def test_series_new_episode_reports_changed(db):
    pid = db.upsert_provider("Plex", "http://plex.invalid", "u", "p")
    sid = db.bulk_import_plex_series(pid, [_show([1])])["created_series_ids"][0]
    r = db.bulk_import_plex_series(pid, [_show([1, 2])])
    assert r["changed_series_ids"] == [sid]
    assert r["created_series_ids"] == []
    assert r["episodes_added"] == 1


def test_series_replaced_episode_file_reports_changed(db):
    pid = db.upsert_provider("Plex", "http://plex.invalid", "u", "p")
    sid = db.bulk_import_plex_series(pid, [_show([1])])["created_series_ids"][0]
    item = _show([1])
    item["episodes"][0]["provider_stream_id"] = "ep-1-new-file"
    r = db.bulk_import_plex_series(pid, [item])
    assert r["changed_series_ids"] == [sid]
    assert r["episodes_added"] == 0


def test_series_detail_change_reports_changed(db):
    pid = db.upsert_provider("Plex", "http://plex.invalid", "u", "p")
    sid = db.bulk_import_plex_series(pid, [_show([1])])["created_series_ids"][0]
    r = db.bulk_import_plex_series(pid, [_show([1], genre="Comedy")])
    assert r["changed_series_ids"] == [sid]


def test_movie_first_import_then_unchanged(db):
    pid = db.upsert_provider("Plex", "http://plex.invalid", "u", "p")
    first = db.bulk_import_plex_movies(pid, [_movie()])
    assert len(first["created_movie_ids"]) == 1
    assert first["changed_movie_ids"] == first["created_movie_ids"]
    again = db.bulk_import_plex_movies(pid, [_movie(last_enriched_at="2")])
    assert again["changed_movie_ids"] == [] and again["created_movie_ids"] == []


def test_movie_detail_change_and_new_file_report_changed(db):
    pid = db.upsert_provider("Plex", "http://plex.invalid", "u", "p")
    mid = db.bulk_import_plex_movies(pid, [_movie()])["created_movie_ids"][0]
    assert db.bulk_import_plex_movies(pid, [_movie(genre="Comedy")])["changed_movie_ids"] == [mid]
    assert db.bulk_import_plex_movies(pid, [_movie(stream="m-2", genre="Comedy")])["changed_movie_ids"] == [mid]


def _fake_bulk(monkeypatch, module):
    monkeypatch.setattr(module.vod_db, "bulk_import_plex_movies", lambda pid, items: {
        "movies_created": 1, "movies_matched": 0, "total": 1,
        "created_movie_ids": [11], "changed_movie_ids": [11, 12]})
    monkeypatch.setattr(module.vod_db, "bulk_import_plex_series", lambda pid, items: {
        "series_created": 0, "series_matched": 1, "episodes_imported": 2, "episodes_added": 1,
        "created_series_ids": [], "changed_series_ids": [21]})


def _assert_ids(r):
    assert sorted(r["created_movie_ids"]) == [11]
    assert sorted(r["changed_movie_ids"]) == [11, 12]
    assert r["created_series_ids"] == []
    assert r["changed_series_ids"] == [21]
    assert r["episodes_added"] == 1


def test_plex_importer_passes_ids_through(db, monkeypatch):
    pid = db.upsert_provider("Plex", "http://plex.invalid", "u", "p", provider_type="plex")
    _fake_bulk(monkeypatch, plex_importer)

    class FakeClient:
        def __init__(self, provider): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def list_libraries(self):
            return [{"type": "movie", "key": "1", "title": "Movies"}, {"type": "show", "key": "2", "title": "TV"}]
        async def list_movies(self, key): return [{"title": "Example Movie", "ratingKey": "5"}]
        async def list_shows(self, key): return [{"title": "Example Show", "ratingKey": "6"}]
        async def list_episodes(self, key): return [{"parentIndex": 1, "index": 1, "title": "Ep"}]

    monkeypatch.setattr(plex_client, "PlexClient", FakeClient)
    monkeypatch.setattr(plex_client, "extract_part", lambda item: ("part", "mkv"))
    _assert_ids(asyncio.run(plex_importer.import_plex_library(pid)))


def test_emby_importer_passes_ids_through(db, monkeypatch):
    pid = db.upsert_provider("Emby", "http://emby.invalid", "u", "p", provider_type="emby")
    _fake_bulk(monkeypatch, emby_vod_importer)

    class FakeClient:
        def __init__(self, provider): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def list_libraries(self):
            return [{"CollectionType": "movies", "ItemId": "1", "Name": "Movies"},
                    {"CollectionType": "tvshows", "ItemId": "2", "Name": "TV"}]
        async def list_movies(self, lib): return [{"Name": "Example Movie", "Id": "5"}]
        async def list_series(self, lib): return [{"Name": "Example Show", "Id": "6"}]
        async def list_episodes(self, sid): return [{"ParentIndexNumber": 1, "IndexNumber": 1, "Name": "Ep"}]

    monkeypatch.setattr(emby_vod_client, "EmbyVodClient", FakeClient)
    monkeypatch.setattr(emby_vod_client, "extract_stream_id", lambda item: ("stream", "mkv"))
    _assert_ids(asyncio.run(emby_vod_importer.import_emby_library(pid)))


def test_library_importer_reports_ids_and_full_resweep_on_removal(db, tmp_path, monkeypatch):
    import os
    import library_importer
    from test_library_importer import _mk, _stub_tmdb, _touch
    _stub_tmdb(monkeypatch)
    pid, root = _mk(db, tmp_path)
    a = _touch(root, "The.Matrix.1999.mkv")
    _touch(root, "Some Home Video (2020).mp4")
    _touch(root, "TV/Breaking Bad (2008)/Season 1/Breaking Bad S01E01.mkv")
    first = asyncio.run(library_importer.import_library(pid))
    assert len(first["created_movie_ids"]) == 2 and len(first["created_series_ids"]) == 1
    assert not first.get("full_resweep")

    _touch(root, "TV/Breaking Bad (2008)/Season 1/Breaking Bad S01E02.mkv")
    again = asyncio.run(library_importer.import_library(pid))
    assert again["changed_movie_ids"] == [] and again["changed_series_ids"] == first["created_series_ids"]
    assert again["episodes_added"] == 1 and not again.get("full_resweep")

    os.remove(a)  # removal cleanup isn't tracked per id, so the resweep must go unscoped
    assert asyncio.run(library_importer.import_library(pid))["full_resweep"] is True


def test_merge_changed_ids_goes_unscoped_on_full_resweep():
    import vod_importer
    assert vod_importer.merge_changed_ids({1}, {"changed_movie_ids": [2]}, "changed_movie_ids") == {1, 2}
    assert vod_importer.merge_changed_ids({1}, {"changed_movie_ids": [2], "full_resweep": True}, "changed_movie_ids") is None


def test_same_file_with_new_size_reports_changed(db):
    """A file replaced in place (same path, e.g. a quality upgrade) is a change;
    an unknown size (None) never is."""
    pid = db.upsert_provider("Plex", "http://plex.invalid", "u", "p")
    mid = db.bulk_import_plex_movies(pid, [_movie(file_size_bytes=100)])["created_movie_ids"][0]
    assert db.bulk_import_plex_movies(pid, [_movie(file_size_bytes=100)])["changed_movie_ids"] == []
    assert db.bulk_import_plex_movies(pid, [_movie(file_size_bytes=200)])["changed_movie_ids"] == [mid]
    assert db.bulk_import_plex_movies(pid, [_movie()])["changed_movie_ids"] == []

    show = _show([1])
    show["episodes"][0]["file_size_bytes"] = 100
    sid = db.bulk_import_plex_series(pid, [show])["created_series_ids"][0]
    show["episodes"][0]["file_size_bytes"] = 200
    r = db.bulk_import_plex_series(pid, [show])
    assert r["changed_series_ids"] == [sid] and r["episodes_added"] == 0


def test_local_library_file_replaced_in_place_reports_changed(db, tmp_path, monkeypatch):
    import library_importer
    from test_library_importer import _mk, _stub_tmdb, _touch
    _stub_tmdb(monkeypatch)
    pid, root = _mk(db, tmp_path)
    _touch(root, "The.Matrix.1999.mkv", size=10)
    mid = asyncio.run(library_importer.import_library(pid))["created_movie_ids"][0]
    _touch(root, "The.Matrix.1999.mkv", size=20)
    assert asyncio.run(library_importer.import_library(pid))["changed_movie_ids"] == [mid]


def test_remote_library_reports_ids_same_as_local(db, monkeypatch):
    """SMB/SFTP/cloud remotes are listed by rclone instead of walked; the
    change reporting after the listing must behave the same."""
    import library_importer
    from test_library_importer import _mk_remote, _stub_tmdb
    _stub_tmdb(monkeypatch)
    pid = _mk_remote(db)
    listing = [("Movies/The.Matrix.1999.mkv", 123), ("TV/Breaking Bad (2008)/Season 1/Breaking Bad S01E01.mkv", 456)]

    async def fake_probe(provider, remote_config):
        return True

    async def fake_list(provider, remote_config):
        return list(listing)
    monkeypatch.setattr(library_importer.rclone_client, "probe", fake_probe)
    monkeypatch.setattr(library_importer.rclone_client, "list_remote", fake_list)

    first = asyncio.run(library_importer.import_library(pid))
    mid, sid = first["created_movie_ids"][0], first["created_series_ids"][0]

    unchanged = asyncio.run(library_importer.import_library(pid))
    assert unchanged["changed_movie_ids"] == [] and unchanged["changed_series_ids"] == []

    listing.append(("TV/Breaking Bad (2008)/Season 1/Breaking Bad S01E02.mkv", 789))
    listing[0] = ("Movies/The.Matrix.1999.mkv", 999)            # replaced in place on the share
    r = asyncio.run(library_importer.import_library(pid))
    assert r["changed_movie_ids"] == [mid] and r["changed_series_ids"] == [sid]
    assert r["episodes_added"] == 1 and not r.get("full_resweep")

    del listing[0]
    assert asyncio.run(library_importer.import_library(pid))["full_resweep"] is True
