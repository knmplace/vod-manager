"""Library handoff to Radarr/Sonarr: add-on-queue step, import watcher, stall notices."""

import asyncio

import pytest

import arr_handoff
import config
import vod_db
import vod_downloader
from arr_client import ArrError


class FakeArr:
    """Stands in for ArrClient. `items` maps tmdb id (or title) -> lookup result."""

    def __init__(self, items=None, fail=False):
        self.items = items or {}
        self.fail = fail
        self.calls = []

    def lookup(self, tmdb_id, title, year):
        self.calls.append(("lookup", tmdb_id, title, year))
        if self.fail:
            raise ArrError("Radarr: can't connect")
        return self.items.get(str(tmdb_id) if tmdb_id else title)

    def add(self, item, root, profile_id, monitor):
        self.calls.append(("add", item.get("title"), root, profile_id, monitor))
        return {**item, "id": 900}

    def names(self):
        return [c[0] for c in self.calls]


@pytest.fixture()
def handoff(db, tmp_path, monkeypatch):
    config.save_download_settings({"enabled": True, "output_dir": str(tmp_path / "library"), "min_free_gb": 0})
    config.save_handoff_settings({"radarr_url": "http://r:7878", "radarr_api_key": "RK",
                                  "sonarr_url": "http://s:8989", "sonarr_api_key": "SK",
                                  "radarr_root": "/MEDIA50/Movies", "radarr_profile_id": 6,
                                  "sonarr_root": "/MEDIA50/Tv", "sonarr_profile_id": 6})
    fakes = {}
    monkeypatch.setattr(arr_handoff, "client_for", lambda kind: fakes.get(kind))
    return fakes


def _set_tmdb(db, table, row_id, tmdb):
    conn = db._connect()
    conn.execute(f"UPDATE {table} SET tmdb_id=? WHERE id=?", (tmdb, row_id))
    conn.commit()
    conn.close()


def _movie(db, name="Some Movie", year=2001, tmdb="777"):
    pid = db.upsert_provider("p1", "http://prov", "u", "pw")
    mid = db.upsert_movie(name, year)
    if tmdb:
        _set_tmdb(db, "movies", mid, tmdb)
    db.add_movie_source(mid, pid, "100", "mp4")
    return mid


def _series(db, episodes=((1, 1),), tmdb="555"):
    pid = db.upsert_provider("p1", "http://prov", "u", "pw")
    sid = db.upsert_series("Show", 2020)
    if tmdb:
        _set_tmdb(db, "series", sid, tmdb)
    for season, num in episodes:
        db.add_episode_source(db.add_episode(sid, season, num, f"e{season}{num}"), pid, f"{season}{num}", "mp4")
    return sid


def _jobs():
    conn = vod_db._connect()
    rows = [dict(r) for r in conn.execute("SELECT * FROM download_jobs ORDER BY id").fetchall()]
    conn.close()
    return rows


def _resolve():
    asyncio.run(arr_handoff.resolve_pending())
    return _jobs()


# ── add-on-queue (T3) ───────────────────────────────────────────────────────

def test_queue_marks_add_only_when_configured(db, tmp_path):
    config.save_download_settings({"enabled": True, "output_dir": str(tmp_path / "lib"), "min_free_gb": 0})
    vod_downloader.enqueue(movie_ids=[_movie(db)])
    assert _jobs()[0]["import_status"] is None
    config.save_handoff_settings({"radarr_url": "http://r:7878", "radarr_api_key": "RK"})
    vod_downloader.enqueue(movie_ids=[_movie(db, name="Other", tmdb="778")])
    assert _jobs()[1]["import_status"] == "add"


def test_existing_title_not_re_added(db, handoff):
    handoff["movie"] = fake = FakeArr({"777": {"title": "Some Movie", "id": 42}})
    vod_downloader.enqueue(movie_ids=[_movie(db)])
    job = _resolve()[0]
    assert "add" not in fake.names()
    assert job["arr_id"] == 42 and job["import_status"] == "ready"


def test_missing_movie_added_unmonitored(db, handoff):
    handoff["movie"] = fake = FakeArr({"777": {"title": "Some Movie"}})
    vod_downloader.enqueue(movie_ids=[_movie(db)])
    job = _resolve()[0]
    assert ("add", "Some Movie", "/MEDIA50/Movies", 6, "unmonitored") in fake.calls
    assert job["arr_id"] == 900 and job["import_status"] == "ready"


def test_missing_show_added_future_only(db, handoff):
    handoff["episode"] = fake = FakeArr({"555": {"title": "Show"}})
    vod_downloader.enqueue(series_ids=[_series(db)])
    _resolve()
    assert ("add", "Show", "/MEDIA50/Tv", 6, "future") in fake.calls


def test_add_step_groups_episodes_by_series(db, handoff):
    handoff["episode"] = fake = FakeArr({"555": {"title": "Show"}})
    vod_downloader.enqueue(series_ids=[_series(db, episodes=((1, 1), (1, 2), (1, 3)))])
    jobs = _resolve()
    assert fake.names().count("lookup") == 1 and fake.names().count("add") == 1
    assert [j["import_status"] for j in jobs] == ["ready"] * 3
    assert {j["arr_id"] for j in jobs} == {900}


def test_no_tmdb_ambiguous_title_needs_manual(db, handoff):
    handoff["movie"] = fake = FakeArr({})          # title lookup finds no single match
    vod_downloader.enqueue(movie_ids=[_movie(db, tmdb=None)])
    job = _resolve()[0]
    assert fake.calls[0] == ("lookup", None, "Some Movie", 2001)
    assert job["import_status"] == "needs_manual"
    assert job["import_note"] == "Add this title to Radarr/Sonarr manually"


def test_arr_unreachable_during_add_retries_next_tick(db, handoff):
    handoff["movie"] = FakeArr(fail=True)
    vod_downloader.enqueue(movie_ids=[_movie(db)])
    job = _resolve()[0]
    assert job["import_status"] == "add" and "can't connect" in job["import_note"]
    handoff["movie"] = FakeArr({"777": {"title": "Some Movie", "id": 42}})
    job = _resolve()[0]
    assert job["import_status"] == "ready" and job["import_note"] is None
