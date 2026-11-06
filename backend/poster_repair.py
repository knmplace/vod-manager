"""Fill missing posters and swap posters on dead image hosts.

KNM: 2026-11-05 - provider image hosts go offline (one host held 523 posters and timed
out on every request), and some titles never had a poster. Images are not stored
locally, but our TMDB store keeps each title's poster path, so most swaps need no API
call. Order: local TMDB store -> TMDB API (reads through the store) -> MDBList (only
when enabled, within its daily quota). A swapped poster is saved and later provider
imports keep it (see vod_db._guard_poster).
"""
import asyncio
import logging
from collections import defaultdict
from urllib.parse import urlsplit

import httpx

import config
import mdblist_artwork
import tmdb_store
import tmdb_sync
import vod_db

logger = logging.getLogger(__name__)

TMDB_IMAGE = "https://image.tmdb.org/t/p/w500"
_SAMPLES_PER_HOST = 3
_MAX_MDBLIST_PER_RUN = 100
_INTERVAL_SECONDS = 24 * 3600
_STARTUP_DELAY_SECONDS = 15 * 60
_TABLES = (("movie", "movies"), ("series", "series"))


def is_tmdb_poster(url: str | None) -> bool:
    return bool(url) and vod_db._usable_provider_poster_url(url) == url and \
        str(url).startswith("https://image.tmdb.org/t/p/")


def _local_poster(kind: str, tmdb_id) -> str | None:
    try:
        path = tmdb_store.get_poster_path("movie" if kind == "movie" else "tv", int(tmdb_id))
    except (TypeError, ValueError):
        return None
    return f"{TMDB_IMAGE}{path}" if path else None


async def _tmdb_poster(kind: str, tmdb_id) -> str | None:
    fetch = tmdb_sync.get_movie_full_details if kind == "movie" else tmdb_sync.get_series_full_details
    try:
        return ((await fetch(str(tmdb_id))) or {}).get("poster_url")
    except tmdb_sync.TmdbNotFoundError:
        return None
    except Exception as exc:
        logger.warning("[poster_repair] TMDB lookup failed for %s %s: %s", kind, tmdb_id, exc)
        return None


def _mdblist_ready() -> bool:
    settings = config.get_mdblist_artwork_settings()
    return bool(settings.get("enabled") and settings.get("account_tier") and config.get_mdblist_api_key())


async def _mdblist_poster(kind: str, item: dict) -> str | None:
    tmdb_id = str(item.get("tmdb_id") or "").strip()
    try:
        if tmdb_id:
            found = await mdblist_artwork.lookup_by_tmdb_id(kind, tmdb_id, item.get("name") or "", item.get("year"))
            found = [c for c in found if c.get("tmdb_id_match")]
        else:
            found = await mdblist_artwork.search_by_title(kind, item.get("name") or "", item.get("year"))
            found = [c for c in found if c.get("identity_match")]
    except (mdblist_artwork.MdblistRateLimitError, ValueError, mdblist_artwork.MdblistApiError) as exc:
        logger.info("[poster_repair] MDBList skipped: %s", exc)
        return None
    return found[0]["poster_url"] if found else None


async def resolve_poster(kind: str, item: dict, *, use_mdblist: bool = True) -> str | None:
    tmdb_id = item.get("tmdb_id")
    if tmdb_id:
        poster = _local_poster(kind, tmdb_id) or await _tmdb_poster(kind, tmdb_id)
        if poster:
            return poster
    if use_mdblist and _mdblist_ready():
        return await _mdblist_poster(kind, item)
    return None


async def _probe_url(url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            async with client.stream("GET", url) as resp:
                return resp.status_code < 400 and resp.headers.get("content-type", "").startswith("image/")
    except Exception:
        return False


def _host(url: str) -> str:
    return urlsplit(url).netloc.lower()


def _rows(table: str) -> list[dict]:
    conn = vod_db._connect()
    try:
        return [dict(r) for r in conn.execute(
            f"SELECT id, name, year, tmdb_id, poster_url FROM {table} WHERE review_excluded=0")]
    finally:
        conn.close()


async def _dead_hosts(by_host: dict[str, list[str]], probe) -> set[str]:
    dead = set()
    for host, urls in by_host.items():
        results = await asyncio.gather(*(probe(u) for u in urls[:_SAMPLES_PER_HOST]))
        if not any(results):
            dead.add(host)
    return dead


_state: dict = {"running": False, "last": None}


def status() -> dict:
    return dict(_state)


async def repair_posters(*, probe=None) -> dict:
    if _state["running"]:
        return {"skipped": "already running"}
    _state["running"] = True
    try:
        _state["last"] = await _repair(probe or _probe_url)
        return _state["last"]
    finally:
        _state["running"] = False


async def _repair(probe) -> dict:
    rows = {kind: await asyncio.to_thread(_rows, table) for kind, table in _TABLES}
    by_host: dict[str, list[str]] = defaultdict(list)
    for items in rows.values():
        for r in items:
            url = vod_db._usable_provider_poster_url(r["poster_url"])
            if url and not is_tmdb_poster(url) and _host(url):
                by_host[_host(url)].append(url)
    dead = await _dead_hosts(by_host, probe)
    out = {"dead_hosts": sorted(dead), "movies_fixed": 0, "series_fixed": 0, "unresolved": 0}
    mdblist_left = _MAX_MDBLIST_PER_RUN
    for kind, items in rows.items():
        for r in items:
            url = vod_db._usable_provider_poster_url(r["poster_url"])
            if url and _host(url) not in dead:  # live host, or a full TMDB poster (never probed)
                continue
            poster = await resolve_poster(kind, r, use_mdblist=False)
            if not poster and mdblist_left > 0 and _mdblist_ready():
                mdblist_left -= 1
                poster = await _mdblist_poster(kind, r)
            if poster and poster != r["poster_url"]:
                await asyncio.to_thread(vod_db.bulk_set_poster_url, kind, [r["id"]], poster)
                out["movies_fixed" if kind == "movie" else "series_fixed"] += 1
            else:
                out["unresolved"] += 1
    logger.info("[poster_repair] %s", out)
    return out


async def repair_loop() -> None:
    await asyncio.sleep(_STARTUP_DELAY_SECONDS)
    while True:
        try:
            await repair_posters()
        except Exception as exc:
            logger.warning("[poster_repair] run failed: %s", exc)
        await asyncio.sleep(_INTERVAL_SECONDS)
