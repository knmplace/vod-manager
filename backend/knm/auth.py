# KNM FORK ONLY - NEVER SEND UPSTREAM
"""Authenticates a request as a Dispatcharr user.

The caller sends its own Dispatcharr API key plus the numeric id of one of vod_manager's
STORED dispatcharr_connections. The key is only ever sent to that stored connection's
URL (never a caller-supplied address, so no SSRF). Dispatcharr user_level 10 = admin."""

import hashlib
import logging
import time

import httpx
from fastapi import Depends, Header, HTTPException

import vod_db
from dispatcharr_client import DispatcharrClient

logger = logging.getLogger(__name__)

ADMIN_LEVEL = 10
CACHE_SECONDS = 60
_cache: dict[tuple, tuple[float, dict]] = {}

# KNM: Dispatcharr allows only 10 failed API key attempts a minute per client IP and then
# answers 429 to everything from vod_manager, so avoid re-sending keys it will refuse 2026-11-25
REJECT_SECONDS = 600
MAX_ENTRIES = 4096  # per map, oldest dropped first, so random keys cannot grow them without limit
_remembered: dict[str, int] = {}  # key sha256 -> id of the connection that accepted it
_rejected: dict[tuple, float] = {}  # (connection id, url, key sha256) -> expiry


class InvalidKey(Exception):
    """Dispatcharr rejected the API key."""


class KeyRejected(InvalidKey):
    """Dispatcharr answered 401/403; the only failure that is negative-cached."""


def clear_cache() -> None:
    _cache.clear()
    _remembered.clear()
    _rejected.clear()


def _key_hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _put(store: dict, key, value) -> None:
    """Insert as the newest entry and drop the oldest ones beyond MAX_ENTRIES."""
    store.pop(key, None)
    store[key] = value
    while len(store) > MAX_ENTRIES:
        del store[next(iter(store))]


async def fetch_me(connection: dict, key: str) -> dict:
    """GET /api/accounts/users/me/ on the stored connection, authenticated with the person's key."""
    client = DispatcharrClient(connection["url"], key)
    try:
        data = await client.get("/api/accounts/users/me/")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403):
            raise KeyRejected() from exc
        raise
    if not isinstance(data, dict) or data.get("id") is None:
        raise InvalidKey()
    return data


class Identity(dict):
    @property
    def is_admin(self) -> bool:
        return bool(self["is_admin"])


async def _validate(connection: dict, key: str) -> dict:
    """Cached /users/me lookup against one stored connection."""
    digest = _key_hash(key)
    ck = (connection["id"], digest)
    now = time.time()
    hit = _cache.get(ck)
    if hit and hit[0] > now:
        return hit[1]
    # KNM: the URL is part of the rejection key so an edited connection starts clean 2026-11-25
    rk = (connection["id"], connection["url"], digest)
    if _rejected.get(rk, 0) > now:
        raise InvalidKey()
    try:
        me = await fetch_me(connection, key)
    except KeyRejected:
        _put(_rejected, rk, now + REJECT_SECONDS)
        raise
    _cache[ck] = (now + CACHE_SECONDS, me)
    return me


def _identity(server_id: int, me: dict) -> Identity:
    level = int(me.get("user_level") or 0)
    return Identity(server_id=server_id, user_id=int(me["id"]), username=me.get("username") or "",
                    user_level=level, is_admin=level >= ADMIN_LEVEL)


async def require_user(x_dispatcharr_key: str | None = Header(default=None),
                       x_dispatcharr_server: str | None = Header(default=None)) -> Identity:
    if not x_dispatcharr_key:
        raise HTTPException(401, "Sign-in required")
    if x_dispatcharr_server:
        try:
            server_id = int(x_dispatcharr_server)
        except ValueError:
            raise HTTPException(401, "Unknown server")
        connection = vod_db.get_dispatcharr_connection(server_id)
        if not connection:
            raise HTTPException(401, "Unknown server")
        candidates = [connection]
    else:
        # no server given: try each STORED connection (never a client URL) until one accepts the key
        candidates = vod_db.list_dispatcharr_connections()
    digest = _key_hash(x_dispatcharr_key)
    if not x_dispatcharr_server:
        # KNM: try the connection that accepted this key last time before any other 2026-11-25
        known = _remembered.get(digest)
        candidates = sorted(candidates, key=lambda c: c["id"] != known)
    unreachable = False
    for connection in candidates:
        try:
            me = await _validate(connection, x_dispatcharr_key)
        except InvalidKey:
            if _remembered.get(digest) == connection["id"]:
                del _remembered[digest]
            continue
        except Exception as exc:
            unreachable = True
            logger.warning("[knm] could not validate key against connection %s: %s",
                           connection.get("id"), type(exc).__name__)
            continue
        if not x_dispatcharr_server:
            _put(_remembered, digest, connection["id"])
        return _identity(int(connection["id"]), me)
    if unreachable:
        raise HTTPException(502, "Could not reach the server")
    raise HTTPException(401, "Invalid key")


async def require_admin(user: Identity = Depends(require_user)) -> Identity:
    if not user.is_admin:
        raise HTTPException(403, "Admin only")
    return user
