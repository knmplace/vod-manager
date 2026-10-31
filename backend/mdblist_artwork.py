"""Opt-in MDBList poster lookup used only by the Missing Artwork review flow.

Public-list sync remains in mdblist_sync.py. This module makes at most one
read request for each explicit artwork-search action and never writes catalog
records; a reviewer applies a candidate through the existing resolve route.
"""

import logging
import re
from urllib.parse import urlsplit

import httpx

import config

logger = logging.getLogger(__name__)
_API_BASE = "https://api.mdblist.com"
_API_KEY_RE = re.compile(r"(apikey=)[^&\s'\"]+")


class MdblistApiError(ValueError):
    pass


class MdblistRateLimitError(MdblistApiError):
    def __init__(self, retry_after: str | None = None):
        self.retry_after = retry_after
        super().__init__("MDBList rate limit reached; wait before searching again")


def _redact(message: str) -> str:
    return _API_KEY_RE.sub(r"\1***", message)


def _https_poster(value) -> str | None:
    if not isinstance(value, str):
        return None
    url = value.strip()
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.netloc or not parsed.path:
        return None
    return url


def _year(value) -> int | None:
    try:
        return int(str(value)[:4]) if value is not None else None
    except (TypeError, ValueError):
        return None


def _normalized_title(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").casefold())


def _candidate(item: dict, *, expected_title: str, expected_year: int | None,
               requested_tmdb_id: str | None = None) -> dict | None:
    ids = item.get("ids") or {}
    raw_tmdb_id = ids.get("tmdb") or item.get("tmdb_id")
    if raw_tmdb_id is None and requested_tmdb_id is not None:
        raw_tmdb_id = requested_tmdb_id
    if raw_tmdb_id is None:
        return None
    poster_url = _https_poster(item.get("poster") or item.get("poster_url"))
    if not poster_url:
        return None

    name = item.get("title") or item.get("name") or ""
    year = _year(item.get("year") or item.get("release_year"))
    title_match = _normalized_title(name) == _normalized_title(expected_title)
    year_match = expected_year is None or year == expected_year
    requested_id_match = requested_tmdb_id is None or str(raw_tmdb_id) == str(requested_tmdb_id)
    identity_match = title_match and year_match and requested_id_match
    return {
        "source": "mdblist",
        "tmdb_id": str(raw_tmdb_id),
        "name": name,
        "year": year,
        "poster_url": poster_url,
        "title_match": title_match,
        "year_match": year_match,
        "tmdb_id_match": requested_id_match,
        "identity_match": identity_match,
        "match_reason": (
            "TMDB ID, title, and year match" if identity_match
            else "MDBList returned a different TMDB ID" if not requested_id_match
            else "title and year match" if title_match and year_match
            else "title matches but year differs" if title_match
            else "title differs; review identity before applying"
        ),
    }


async def _get_json(path: str, params: dict) -> tuple[object, dict]:
    api_key = config.get_mdblist_api_key()
    if not api_key:
        raise MdblistApiError("MDBList API key is not configured")
    config.reserve_mdblist_artwork_request()
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(
                f"{_API_BASE}{path}",
                params={**params, "apikey": api_key},
            )
        try:
            config.record_mdblist_artwork_rate_headers(response.headers)
        except Exception as exc:
            logger.warning("[mdblist_artwork] could not persist rate-limit headers: %s", _redact(str(exc)))
        if response.status_code == 429:
            raise MdblistRateLimitError(response.headers.get("Retry-After"))
        response.raise_for_status()
        return response.json(), dict(response.headers)
    except MdblistRateLimitError:
        raise
    except httpx.HTTPStatusError as exc:
        safe_message = _redact(str(exc))
        logger.warning("[mdblist_artwork] request failed: %s", safe_message)
        raise MdblistApiError("MDBList artwork lookup failed") from exc
    except httpx.HTTPError as exc:
        safe_message = _redact(str(exc))
        logger.warning("[mdblist_artwork] request failed: %s", safe_message)
        raise MdblistApiError("MDBList artwork lookup could not connect") from exc


async def lookup_by_tmdb_id(content_type: str, tmdb_id: str, title: str,
                            year: int | None) -> list[dict]:
    media_type = "movie" if content_type == "movie" else "show"
    payload, _ = await _get_json(f"/tmdb/{media_type}/{tmdb_id}/", {})
    if not isinstance(payload, dict):
        return []
    candidate = _candidate(payload, expected_title=title, expected_year=year,
                           requested_tmdb_id=str(tmdb_id))
    return [candidate] if candidate else []


async def search_by_title(content_type: str, title: str, year: int | None) -> list[dict]:
    media_type = "movie" if content_type == "movie" else "show"
    params = {"query": title, "limit": 10}
    if year is not None:
        params["year"] = year
    payload, _ = await _get_json(f"/search/{media_type}", params)
    raw_items = payload.get("search", []) if isinstance(payload, dict) else payload
    if not isinstance(raw_items, list):
        return []
    candidates = [
        candidate for item in raw_items if isinstance(item, dict)
        if (candidate := _candidate(item, expected_title=title, expected_year=year)) is not None
    ]
    candidates.sort(key=lambda item: (not item["identity_match"], not item["title_match"], item["year"] is None))
    return candidates[:10]
