# KNM FORK ONLY - NEVER SEND UPSTREAM
"""/api/knm/admin/*: the vod_manager admin page. Guarded by the existing admin login
(X-Session-Token), NOT by a Dispatcharr key."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException

import arr_handoff
from knm import service, store
from knm.routes_models import AllowlistUpdate
from routes import require_auth

router = APIRouter(prefix="/admin", dependencies=[Depends(require_auth)])


async def _run(fn, *args):
    try:
        return await asyncio.to_thread(fn, *args)
    except service.KnmError as exc:
        raise HTTPException(exc.code, exc.message)


def _allowlist() -> dict:
    return {"default_cap": store.default_cap(), "entries": store.list_entries()}


@router.get("/allowlist")
async def get_allowlist():
    return await asyncio.to_thread(_allowlist)


@router.put("/allowlist")
async def put_allowlist(body: AllowlistUpdate):
    def work():
        if body.default_cap is not None:
            store.set_default_cap(body.default_cap)
        for e in body.entries:
            store.upsert_entry(e.server_id, e.user_id, e.username, e.allowed, e.daily_cap)
        return _allowlist()
    return await asyncio.to_thread(work)


@router.delete("/allowlist/{server_id}/{user_id}")
async def delete_entry(server_id: int, user_id: int):
    if not await asyncio.to_thread(store.delete_entry, server_id, user_id):
        raise HTTPException(404, "Not on the allow-list")
    return await asyncio.to_thread(_allowlist)


@router.get("/requests")
async def requests(status: str | None = None):
    return await asyncio.to_thread(service.admin_requests, status)


@router.post("/requests/{rid}/retry")
async def retry(rid: int):
    req = await _run(service._get_request, rid)
    for jid in await asyncio.to_thread(service.retryable_import_jobs, req):
        await arr_handoff.retry_import(jid)
    out = await _run(service.admin_retry, rid)
    return service.public_view(out, True)


@router.post("/requests/{rid}/cancel")
async def cancel(rid: int):
    return service.public_view(await _run(service.admin_cancel, rid), True)


@router.get("/notices")
async def get_notices():
    return {"notices": await asyncio.to_thread(service.admin_notices)}


@router.post("/notices/clear")
async def clear_notices():
    return {"cleared": await asyncio.to_thread(service.admin_clear_notices)}
