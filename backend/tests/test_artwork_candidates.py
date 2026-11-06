# KNM: 2026-11-06 - poster search must always offer several posters to pick from (the
# exact-title search alone gave "A Hard Place" one wrong 2013 short). Widen with the
# provider's own title/year, then cast credits, then a looser title search; the
# provider's own poster is offered last.
import asyncio

import pytest

import artwork_candidates as ac
import tmdb_sync


def _c(tmdb_id, poster=True, year=2025):
    return {"tmdb_id": str(tmdb_id), "name": f"T{tmdb_id}", "year": year,
            "poster_url": f"https://image.tmdb.org/t/p/w185/{tmdb_id}.jpg" if poster else None}


HINTS = {"name": "A Hard Place", "year": 2025, "cast": ["Felissa Rose", "Sadie Katz", "Lynn Lowry", "X"],
         "plot": "plot", "poster_url": "http://provider.example/p.jpg"}


@pytest.fixture()
def calls(monkeypatch):
    log = []
    answers = {"base": [_c(1, year=2013)], "hint": [_c(1, year=2013), _c(2)],
               "cast": [_c(3), _c(2)], "loose": [_c(4), _c(5, poster=False), _c(6)]}

    async def search(query, ct, year=None, *, exact_only=True, limit=5):
        key = "loose" if not exact_only else ("hint" if year == 2025 else "base")
        log.append((key, query, year))
        return list(answers[key])

    async def cast(ct, names, year):
        log.append(("cast", tuple(names), year))
        return list(answers["cast"])

    async def hints(ct, item_id):
        log.append(("hints", ct, item_id))
        return dict(HINTS)

    monkeypatch.setattr(tmdb_sync, "search_title", search)
    monkeypatch.setattr(tmdb_sync, "cast_titles", cast)
    monkeypatch.setattr(ac, "provider_hints", hints)
    return {"log": log, "answers": answers}


ITEM = {"id": 7, "name": "A Hard Place", "year": 2013}


def test_widens_until_enough_posters_and_dedupes(calls):
    out = asyncio.run(ac.gather("movie", ITEM, include_provider=False))
    assert [c["tmdb_id"] for c in out] == ["1", "2", "3", "4", "6", "5"]
    assert out[-1]["poster_url"] is None  # no-poster entries go last
    assert [k[0] for k in calls["log"]] == ["base", "hints", "hint", "cast", "loose"]
    assert ("cast", ("Felissa Rose", "Sadie Katz", "Lynn Lowry"), 2025) in calls["log"]


def test_stops_widening_once_four_posters(calls):
    calls["answers"]["cast"] = [_c(3), _c(8)]
    out = asyncio.run(ac.gather("movie", ITEM, include_provider=False))
    assert [c["tmdb_id"] for c in out] == ["1", "2", "3", "8"]
    assert "loose" not in [k[0] for k in calls["log"]]


def test_no_widening_or_provider_call_when_base_has_enough(calls):
    calls["answers"]["base"] = [_c(i) for i in range(1, 5)]
    out = asyncio.run(ac.gather("movie", ITEM, include_provider=False))
    assert len(out) == 4 and [k[0] for k in calls["log"]] == ["base"]


def test_provider_poster_offered_last(calls):
    calls["answers"]["base"] = [_c(i) for i in range(1, 5)]
    out = asyncio.run(ac.gather("movie", ITEM, include_provider=True))
    assert out[-1] == {"source": "provider", "tmdb_id": None, "name": "A Hard Place", "year": 2025,
                       "poster_url": "http://provider.example/p.jpg", "overview": "plot",
                       "cast": ["Felissa Rose", "Sadie Katz", "Lynn Lowry", "X"], "vote_average": None,
                       "season_count": None, "episode_count": None}
    assert all(c.get("source") != "provider" for c in out[:-1])


def test_failing_step_does_not_break_result(calls, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("tmdb down")
    monkeypatch.setattr(tmdb_sync, "cast_titles", boom)
    out = asyncio.run(ac.gather("movie", ITEM, include_provider=False))
    assert [c["tmdb_id"] for c in out] == ["1", "2", "4", "6", "5"]


def test_capped(calls):
    calls["answers"]["loose"] = [_c(i) for i in range(10, 30)]
    out = asyncio.run(ac.gather("movie", ITEM, include_provider=True))
    assert len(out) == ac.MAX_CANDIDATES + 1 and out[-1]["source"] == "provider"


def test_parse_hints_movie_and_series():
    movie = {"info": {"name": "A Hard Place (2025)", "releasedate": "2025-01-12", "cast": "A, B ,C",
                      "director": "J. Horton", "plot": "p", "movie_image": "http://x/m.jpg"},
             "movie_data": {"name": "A Hard Place (2025)"}}
    h = ac.parse_hints("movie", movie)
    assert (h["name"], h["year"], h["cast"], h["poster_url"]) == ("A Hard Place", 2025, ["A", "B", "C"], "http://x/m.jpg")
    series = {"info": {"name": "Show", "releaseDate": "2019-03-01", "cast": "", "cover": "http://x/c.jpg"}}
    h = ac.parse_hints("series", series)
    assert (h["name"], h["year"], h["cast"], h["poster_url"]) == ("Show", 2019, [], "http://x/c.jpg")
    assert ac.parse_hints("movie", {}) is None


def test_cast_titles_year_window_and_ranking(monkeypatch):
    credits = {
        101: [{"id": 1, "title": "Near", "release_date": "2024-05-01", "poster_path": "/a.jpg"},
              {"id": 2, "title": "Shared", "release_date": "2025-02-01", "poster_path": "/b.jpg"},
              {"id": 3, "title": "Old", "release_date": "2010-01-01", "poster_path": "/c.jpg"}],
        102: [{"id": 2, "title": "Shared", "release_date": "2025-02-01", "poster_path": "/b.jpg"}],
    }

    async def fetch(kind, query, year, url, params, found):
        if kind == "search/person":
            return {"results": [{"id": 101 if query == "A" else 102}]}, True
        pid = int(url.split("/person/")[1].split("/")[0])
        return {"cast": credits[pid]}, True

    async def payload(*a, **k):
        return {}
    monkeypatch.setattr(tmdb_sync, "_kept_or_fetch", fetch)
    monkeypatch.setattr(tmdb_sync, "fetch_title_payload", payload)
    monkeypatch.setattr(tmdb_sync, "get_tmdb_api_key", lambda: "k")
    out = asyncio.run(tmdb_sync.cast_titles("movie", ["A", "B"], 2025))
    assert [c["tmdb_id"] for c in out] == ["2", "1"]
    assert out[0]["poster_url"] == "https://image.tmdb.org/t/p/w185/b.jpg"


def test_cast_titles_without_key_is_empty(monkeypatch):
    monkeypatch.setattr(tmdb_sync, "get_tmdb_api_key", lambda: "")
    assert asyncio.run(tmdb_sync.cast_titles("movie", ["A"], 2025)) == []


def test_search_title_loose_keeps_fuzzy_results(monkeypatch):
    rows = [{"tmdb_id": 1, "title": "A Hard Place", "release_date": "2013-01-01", "poster_path": "/1.jpg"},
            {"tmdb_id": 2, "title": "Between a Rock and a Hard Place", "release_date": "2020-01-01", "poster_path": "/2.jpg"}]

    async def local(media_type, query, year=None, limit=10):
        return rows

    async def payload(*a, **k):
        return {}

    async def noted(hit):
        return None
    monkeypatch.setattr(tmdb_sync, "search_local", local)
    monkeypatch.setattr(tmdb_sync, "fetch_title_payload", payload)
    monkeypatch.setattr(tmdb_sync, "note_lookup", noted)
    exact = asyncio.run(tmdb_sync.search_title("A Hard Place", "movie"))
    loose = asyncio.run(tmdb_sync.search_title("A Hard Place", "movie", exact_only=False))
    assert [c["tmdb_id"] for c in exact] == ["1"]
    assert [c["tmdb_id"] for c in loose] == ["1", "2"]
