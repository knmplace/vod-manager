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


async def require_user(x_dispatcharr_key: str | None = Header(default=None),
                       x_dispatcharr_server: str | None = Header(default=None)) -> Identity:
    if not x_dispatcharr_key or not x_dispatcharr_server:
        raise HTTPException(401, "Sign-in required")
    try:
        server_id = int(x_dispatcharr_server)
    except ValueError:
        raise HTTPException(401, "Unknown server")
    connection = vod_db.get_dispatcharr_connection(server_id)
    if not connection:
        raise HTTPException(401, "Unknown server")
    ck = (server_id, hashlib.sha256(x_dispatcharr_key.encode()).hexdigest())
    now = time.time()
    hit = _cache.get(ck)
    if hit and hit[0] > now:
        me = hit[1]
    else:
        try:
            me = await fetch_me(connection, x_dispatcharr_key)
        except InvalidKey:
            raise HTTPException(401, "Invalid key")
        except Exception as exc:
            logger.warning("[knm] could not validate key against connection %s: %s", server_id, type(exc).__name__)
            raise HTTPException(502, "Could not reach the server")
        _cache[ck] = (now + CACHE_SECONDS, me)
    return Identity(server_id=server_id, user_id=int(me["id"]), username=me.get("username") or "",
                    user_level=int(me.get("user_level") or 0),
                    is_admin=int(me.get("user_level") or 0) >= ADMIN_LEVEL)


async def require_admin(user: Identity = Depends(require_user)) -> Identity:
    if not user.is_admin:
        raise HTTPException(403, "Admin only")
    return user
