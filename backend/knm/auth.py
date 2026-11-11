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


class InvalidKey(Exception):
    """Dispatcharr rejected the API key."""


def clear_cache() -> None:
    _cache.clear()


async def fetch_me(connection: dict, key: str) -> dict:
    """GET /api/accounts/users/me/ on the stored connection, authenticated with the person's key."""
    client = DispatcharrClient(connection["url"], key)
    try:
        data = await client.get("/api/accounts/users/me/")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403):
            raise InvalidKey() from exc
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
    ck = (connection["id"], hashlib.sha256(key.encode()).hexdigest())
    now = time.time()
    hit = _cache.get(ck)
    if hit and hit[0] > now:
        return hit[1]
    me = await fetch_me(connection, key)
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
    unreachable = False
    for connection in candidates:
        try:
            me = await _validate(connection, x_dispatcharr_key)
        except InvalidKey:
            continue
        except Exception as exc:
            unreachable = True
            logger.warning("[knm] could not validate key against connection %s: %s",
                           connection.get("id"), type(exc).__name__)
            continue
        return _identity(int(connection["id"]), me)
    if unreachable:
        raise HTTPException(502, "Could not reach the server")
    raise HTTPException(401, "Invalid key")


async def require_admin(user: Identity = Depends(require_user)) -> Identity:
    if not user.is_admin:
        raise HTTPException(403, "Admin only")
    return user
