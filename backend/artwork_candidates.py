"""Poster choices for Missing Artwork and Needs Review.

KNM: 2026-11-06 - the exact-title search can return a single wrong title (for "A Hard
Place" (2025) TMDB's only exact hit was a 2013 short), leaving no real poster to pick.
When fewer than MIN_POSTERS results have a poster, widen in order: the provider's own
title/year, titles the provider's cast share near that year, then a looser title search.
The provider's own poster is offered last, so TMDB indices stay the same for AI suggest.
Provider details are fetched only when a user opens the row (a card open) and kept an hour.
"""
import asyncio
import logging
import re
import time

import tmdb_sync
import vod_db
import vod_importer

logger = logging.getLogger(__name__)

MIN_POSTERS = 4
MAX_CANDIDATES = 8
_HINT_TTL = 3600
_hint_cache: dict[tuple[str, int], tuple[float, dict | None]] = {}


def _year(*values) -> int | None:
    for v in values:
        m = re.match(r"\s*(\d{4})", str(v or ""))
        if m and 1900 <= int(m.group(1)) <= 2100:
            return int(m.group(1))
    return None


def parse_hints(content_type: str, payload: dict) -> dict | None:
    info = (payload or {}).get("info")
    if not isinstance(info, dict) or not info:
        return None
    data = payload.get("movie_data") if isinstance(payload.get("movie_data"), dict) else {}
    raw = info.get("o_name") or info.get("name") or data.get("name") or ""
    name, name_year = vod_importer.parse_name_year(raw) if raw else ("", None)
    poster_keys = ("movie_image", "cover_big", "stream_icon", "cover") if content_type == "movie" \
        else ("cover", "cover_big", "movie_image", "stream_icon")
    return {
        "name": name or None,
        "year": _year(info.get("releasedate"), info.get("releaseDate"), info.get("year")) or name_year,
        "cast": [c.strip() for c in str(info.get("cast") or info.get("actors") or "").split(",") if c.strip()],
        "director": info.get("director") or None,
        "plot": info.get("plot") or info.get("description") or None,
        "poster_url": next((info[k] for k in poster_keys if info.get(k)), None),
    }


async def _fetch_hints(content_type: str, item_id: int) -> dict | None:
    lister = vod_db.list_movie_sources if content_type == "movie" else vod_db.list_series_sources
    id_key = "provider_stream_id" if content_type == "movie" else "provider_series_id"
    for source in await asyncio.to_thread(lister, item_id):
        if not source.get("provider_is_active") or not source.get(id_key):
            continue
        provider = await asyncio.to_thread(vod_db.get_provider, source["provider_id"])
        if not provider or (provider.get("provider_type") or "xc") != "xc":
            continue
        client = vod_importer.XCProviderClient(provider)
        call = client.get_vod_info if content_type == "movie" else client.get_series_info
        try:
            return parse_hints(content_type, await asyncio.wait_for(call(str(source[id_key])), 15))
        except Exception as exc:
            logger.info("[artwork_candidates] provider details failed for %s %s: %s", content_type, item_id, exc)
    return None


async def provider_hints(content_type: str, item_id: int) -> dict | None:
    key = (content_type, int(item_id))
    hit = _hint_cache.get(key)
    if hit and time.time() - hit[0] < _HINT_TTL:
        return hit[1]
    hints = await _fetch_hints(content_type, item_id)
    _hint_cache[key] = (time.time(), hints)
    return hints


def _posters(rows: list[dict]) -> int:
    return sum(1 for r in rows if r.get("poster_url"))


async def gather(content_type: str, item: dict, q: str | None = None, *, year: int | None = None,
                 include_provider: bool = True) -> list[dict]:
    query = vod_db.tmdb_review_search_query(item["name"], q)
    rows = list(await tmdb_sync.search_title(query, content_type, year=year))  # errors reach the route
    hints = None

    def add(found):
        seen = {r.get("tmdb_id") for r in rows}
        rows.extend(r for r in found or [] if r.get("tmdb_id") not in seen)

    if _posters(rows) < MIN_POSTERS or include_provider:
        try:
            hints = await provider_hints(content_type, item["id"])
        except Exception as exc:
            logger.info("[artwork_candidates] provider hints failed: %s", exc)
    hint_year = (hints or {}).get("year")
    steps = []
    if hints and hints.get("name") and (hints["name"] != query or hint_year != year):
        steps.append(lambda: tmdb_sync.search_title(hints["name"], content_type, year=hint_year))
    if hints and hints.get("cast"):
        steps.append(lambda: tmdb_sync.cast_titles(content_type, hints["cast"][:3], hint_year or item.get("year")))
    steps.append(lambda: tmdb_sync.search_title(query, content_type, exact_only=False, limit=MAX_CANDIDATES))
    for step in steps:
        if _posters(rows) >= MIN_POSTERS:
            break
        try:
            add(await step())
        except Exception as exc:
            logger.info("[artwork_candidates] widening step failed: %s", exc)
    rows.sort(key=lambda r: not r.get("poster_url"))  # stable: posters first
    rows = rows[:MAX_CANDIDATES]
    if include_provider and hints and hints.get("poster_url"):
        rows.append({
            "source": "provider", "tmdb_id": None,
            "name": hints.get("name") or item.get("name"), "year": hint_year or item.get("year"),
            "poster_url": hints["poster_url"], "overview": hints.get("plot"),
            "cast": hints.get("cast", [])[:4], "vote_average": None,
            "season_count": None, "episode_count": None,
        })
    return rows
