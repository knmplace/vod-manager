# KNM FORK ONLY - NEVER SEND UPSTREAM
"""/api/knm/* (phase 1): me, download, downloads, notices, allowlist."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from knm import admin_routes, service, store
from knm.routes_models import AckRequest, AllowlistUpdate, DownloadRequest
from knm.auth import Identity, require_admin, require_user

router = APIRouter(prefix="/api/knm", tags=["knm"])
router.include_router(admin_routes.router)


@router.get("/me")
async def me(user: Identity = Depends(require_user)):
    def work():
        allowed, cap = service.access(user)
        return {"user_id": user["user_id"], "username": user["username"], "server_id": user["server_id"],
                "is_admin": user.is_admin, "allowed": allowed, "cap": cap,
                "used_today": store.used_today(user["server_id"], user["user_id"])}
    return await asyncio.to_thread(work)


@router.post("/download")
async def download(body: DownloadRequest, user: Identity = Depends(require_user)):
    if body.kind not in service.KINDS:
        raise HTTPException(422, "kind must be movie or show")
    try:
        req = await asyncio.to_thread(service.create_request, user, body.kind, body.title, body.year, body.tmdb_id)
    except service.KnmError as exc:
        raise HTTPException(exc.code, exc.message)
    return service.public_view(req, user.is_admin)


@router.get("/downloads")
async def downloads(all: int = 0, user: Identity = Depends(require_user)):
    return {"downloads": await asyncio.to_thread(service.list_requests, user, bool(all))}


@router.get("/notices")
async def get_notices(user: Identity = Depends(require_user)):
    return {"notices": await asyncio.to_thread(service.list_notices, user)}


@router.post("/notices/ack")
async def ack(body: AckRequest, user: Identity = Depends(require_user)):
    return {"acknowledged": await asyncio.to_thread(service.ack_notices, user, body.ids)}


@router.get("/allowlist")
async def get_allowlist(user: Identity = Depends(require_admin)):
    def work():
        return {"default_cap": store.default_cap(), "entries": store.list_entries()}
    return await asyncio.to_thread(work)


@router.put("/allowlist")
async def put_allowlist(body: AllowlistUpdate, user: Identity = Depends(require_admin)):
    def work():
        if body.default_cap is not None:
            store.set_default_cap(body.default_cap)
        for e in body.entries:
            store.upsert_entry(e.server_id, e.user_id, e.username, e.allowed, e.daily_cap)
        return {"default_cap": store.default_cap(), "entries": store.list_entries()}
    return await asyncio.to_thread(work)
