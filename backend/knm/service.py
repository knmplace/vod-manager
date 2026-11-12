# KNM FORK ONLY - NEVER SEND UPSTREAM
"""Request lifecycle: match a title to a vod_manager item, enqueue through the existing
downloader, derive status from the jobs, and raise notices on Ready / Failed."""

import json
import logging
import re
import time

import notices
import vod_db
import vod_downloader
from knm import status as st
from knm import store

logger = logging.getLogger(__name__)

KINDS = {"movie": "movie", "show": "series"}      # request kind -> vod_manager item kind


class KnmError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code, self.message = code, message


# -- matching ----------------------------------------------------------------

def _norm(text: str | None) -> str:
    return re.sub(r"[\W_]+", "", re.sub(r"\s*\((?:18|19|20)\d{2}\)\s*$", "", text or "").casefold())


def _has_source(item_kind: str, item_id: int) -> bool:
    if item_kind == "movie":
        return bool(vod_db.list_movie_sources_for_streaming(item_id))
    return any(vod_db.list_episode_sources_for_streaming(e["id"]) for e in vod_db.list_episodes(item_id))


def match_item(kind: str, title: str, year: int | None, tmdb_id) -> dict | None:
    """Prefer the TMDB id; fall back to normalised title plus the SAME year (never title alone).
    Among several catalog rows, one that has a playable source wins."""
    item_kind = KINDS[kind]
    table = "movies" if item_kind == "movie" else "series"
    conn = vod_db._connect()
    try:
        cands: list[dict] = []
        if tmdb_id not in (None, ""):
            cands = [dict(r) for r in conn.execute(
                f"SELECT id, name, year, tmdb_id FROM {table} WHERE tmdb_id=? ORDER BY id", (str(tmdb_id),))]
        if not cands and year:
            want = _norm(title)
            named = [dict(r) for r in conn.execute(
                f"SELECT id, name, year, tmdb_id FROM {table} WHERE year BETWEEN ? AND ? ORDER BY id",
                (int(year) - 1, int(year) + 1)) if _norm(r["name"]) == want]
            # exact year first, then +/-1 (providers often disagree by a year)
            cands = sorted(named, key=lambda c: (c["year"] != int(year), c["id"]))
    finally:
        conn.close()
    for c in cands:
        if _has_source(item_kind, c["id"]):
            return {"item_kind": item_kind, "item_id": c["id"], "tmdb_id": c.get("tmdb_id")}
    return None


# -- enqueue -----------------------------------------------------------------

def _max_job_id() -> int:
    conn = vod_db._connect()
    try:
        return conn.execute("SELECT COALESCE(MAX(id),0) m FROM download_jobs").fetchone()["m"]
    finally:
        conn.close()


def _job_ids_for(item_kind: str, item_id: int, after_id: int) -> list[int]:
    if item_kind == "movie":
        kind, ids = "movie", [item_id]
    else:
        kind, ids = "episode", [e["id"] for e in vod_db.list_episodes(item_id)]
    if not ids:
        return []
    conn = vod_db._connect()
    try:
        out = []
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            q = ("SELECT id FROM download_jobs WHERE kind=? AND item_id IN (" + ",".join("?" for _ in chunk)
                 + ") AND (id>? OR status IN ('queued','running')) ORDER BY id")
            out += [r["id"] for r in conn.execute(q, (kind, *chunk, after_id))]
        return out
    finally:
        conn.close()


def _in_library(item_kind: str, item_id: int) -> bool:
    return bool(vod_db.presence_labels(item_kind, [item_id]))


def create_request(user: dict, kind: str, title: str, year: int | None, tmdb_id) -> dict:
    if kind not in KINDS:
        raise KnmError(422, "kind must be movie or show")
    allowed, cap = access(user)
    if not allowed:
        raise KnmError(403, "Downloads are not enabled for your account")
    match = match_item(kind, title, year, tmdb_id)
    if not match:
        raise KnmError(404, "That title isn't available to download")
    key = store.name_key(user.get("username"))
    who, args = (("lower(trim(username))=?", (key,)) if key
                 else ("server_id=? AND user_id=?", (user["server_id"], user["user_id"])))
    dup = store.one(f"SELECT * FROM knm_requests WHERE {who} AND item_kind=? AND item_id=? "
                    "AND status NOT IN ('failed','cancelled') ORDER BY id DESC",
                    (*args, match["item_kind"], match["item_id"]))
    if dup:
        return sync_request(dup)
    if store.used_today(user["server_id"], user["user_id"], username=user.get("username")) >= cap:
        raise KnmError(429, f"Daily limit of {cap} titles reached")

    now = time.time()
    jobs: list[int] = []
    if not _in_library(match["item_kind"], match["item_id"]):
        before = _max_job_id()
        try:
            if match["item_kind"] == "movie":
                res = vod_downloader.enqueue(movie_ids=[match["item_id"]])
            else:
                res = vod_downloader.enqueue(series_ids=[match["item_id"]])
        except ValueError as exc:
            logger.warning("[knm] enqueue refused for %r: %s", title, exc)
            raise KnmError(409, "Downloads are not available right now")
        jobs = _job_ids_for(match["item_kind"], match["item_id"], before)
        if not jobs:
            logger.warning("[knm] nothing queued for %r (%s)", title, res)
            raise KnmError(404, "That title isn't available to download")
    rid = store.write(
        "INSERT INTO knm_requests (server_id, user_id, username, kind, title, year, tmdb_id, item_kind, item_id, "
        "job_ids, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (user["server_id"], user["user_id"], user.get("username"), kind, title, year,
         str(match["tmdb_id"]) if match.get("tmdb_id") else (str(tmdb_id) if tmdb_id else None),
         match["item_kind"], match["item_id"], json.dumps(jobs), "queued", now, now))
    logger.info("[knm] request %s: user=%s/%s %s %r -> %s %s jobs=%s", rid, user["server_id"], user["user_id"],
                kind, title, match["item_kind"], match["item_id"], jobs)
    return sync_request(store.one("SELECT * FROM knm_requests WHERE id=?", (rid,)))


def access(user: dict) -> tuple[bool, int]:
    """(allowed, daily cap), keyed on the lowercased/trimmed username across all servers (see
    store.find_by_username for how duplicate rows combine). Admins (Dispatcharr level 10) are always allowed; the cap still applies."""
    entry = store.find_by_username(user.get("username"))
    if entry is None and not store.name_key(user.get("username")):
        entry = store.get_entry(user["server_id"], user["user_id"])   # no username: legacy id key
    cap = entry["daily_cap"] if entry and entry["daily_cap"] is not None else store.default_cap()
    return bool(user.get("is_admin") or (entry and entry["allowed"])), cap


# -- status ------------------------------------------------------------------

def _jobs(ids: list[int]) -> list[dict]:
    return [j for j in (vod_db.get_download_job(i) for i in ids) if j]


def sync_request(req: dict) -> dict:
    """Recomputes status from the live jobs, persists changes, raises notices on transitions."""
    now = time.time()
    d = st.derive(_jobs(store.decode_jobs(req)), _in_library(req["item_kind"], req["item_id"]), now)
    new = d["status"]
    if (new, d["progress"], d["detail"], d["episodes_ready"], d["episodes_total"]) != (
            req["status"], req["progress"], req["detail"], req["episodes_ready"], req["episodes_total"]):
        store.write("UPDATE knm_requests SET status=?, progress=?, detail=?, episodes_ready=?, episodes_total=?, "
                    "updated_at=?, completed_at=? WHERE id=?",
                    (new, d["progress"], d["detail"], d["episodes_ready"], d["episodes_total"], now,
                     now if new in st.TERMINAL else None, req["id"]))
    req = {**req, **{k: d[k] for k in ("progress", "detail", "episodes_ready", "episodes_total")}, "status": new}
    if new in ("ready", "failed"):
        _notify(req, new)
    return req


def _notify(req: dict, kind: str) -> None:
    exists = store.one("SELECT 1 x FROM knm_notices WHERE request_id=? AND kind=?", (req["id"], kind))
    if exists:
        return
    store.write("INSERT OR IGNORE INTO knm_notices (request_id, server_id, user_id, username, kind, title, req_kind, "
                "tmdb_id, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (req["id"], req["server_id"], req["user_id"], req.get("username"), kind, req["title"], req["kind"],
                 req.get("tmdb_id"), time.time()))
    if kind == "failed":
        body = f"{req.get('username') or req['user_id']} requested {req['title']}. {req.get('detail') or ''}".strip()
        logger.error("[knm] request %s FAILED (%s): %s", req["id"], req["title"], req.get("detail"))
        first = (store.decode_jobs(req) or [None])[0]
        notices.add("knm_download", "error", f"Download failed: {req['title']}", body, job_id=first)


def sync_active() -> None:
    """Syncs every request that can still change, so failures are noticed for everybody on any poll."""
    for req in store.rows("SELECT * FROM knm_requests WHERE status NOT IN ('ready','cancelled')"):
        try:
            sync_request(req)
        except Exception:
            logger.exception("[knm] sync of request %s failed", req.get("id"))


def public_view(req: dict, admin: bool) -> dict:
    out = {"id": req["id"], "kind": req["kind"], "title": req["title"], "year": req["year"],
           "tmdb_id": req["tmdb_id"], "status": req["status"], "label": st.LABELS.get(req["status"], req["status"]),
           "progress": req["progress"], "episodes_total": req["episodes_total"],
           "episodes_ready": req["episodes_ready"], "created_at": req["created_at"],
           "updated_at": req["updated_at"]}
    if admin:
        out.update(detail=req["detail"], username=req["username"], user_id=req["user_id"],
                   server_id=req["server_id"], job_ids=store.decode_jobs(req))
    return out


def list_requests(user: dict, all_users: bool) -> list[dict]:
    sync_active()
    if all_users and user["is_admin"]:
        rows = store.rows("SELECT * FROM knm_requests ORDER BY id DESC LIMIT 500")
    else:
        rows = store.rows("SELECT * FROM knm_requests WHERE server_id=? AND user_id=? ORDER BY id DESC LIMIT 200",
                          (user["server_id"], user["user_id"]))
    return [public_view(r, bool(all_users and user["is_admin"])) for r in rows]


def list_notices(user: dict) -> list[dict]:
    sync_active()
    mine = store.rows("SELECT * FROM knm_notices WHERE server_id=? AND user_id=? AND read_at IS NULL ORDER BY id DESC",
                      (user["server_id"], user["user_id"]))
    out = [{"id": n["id"], "kind": n["kind"], "title": n["title"], "req_kind": n["req_kind"],
            "tmdb_id": n["tmdb_id"], "request_id": n["request_id"], "created_at": n["created_at"],
            "username": n["username"]} for n in mine]
    if user["is_admin"]:
        seen = {n["id"] for n in mine}
        others = store.rows("SELECT * FROM knm_notices WHERE kind='failed' AND admin_read_at IS NULL "
                            "AND NOT (server_id=? AND user_id=?) ORDER BY id DESC",
                            (user["server_id"], user["user_id"]))
        out += [{"id": n["id"], "kind": n["kind"], "title": n["title"], "req_kind": n["req_kind"],
                 "tmdb_id": n["tmdb_id"], "request_id": n["request_id"], "created_at": n["created_at"],
                 "username": n["username"]} for n in others if n["id"] not in seen]
    return out


def ack_notices(user: dict, ids: list[int]) -> int:
    n = 0
    for i in ids:
        n += _ack(user, int(i))
    return n


def _ack(user: dict, nid: int) -> int:
    row = store.one("SELECT * FROM knm_notices WHERE id=?", (nid,))
    if not row:
        return 0
    now = time.time()
    if row["server_id"] == user["server_id"] and row["user_id"] == user["user_id"]:
        store.write("UPDATE knm_notices SET read_at=? WHERE id=?", (now, nid))
        return 1
    if user["is_admin"] and row["kind"] == "failed":
        store.write("UPDATE knm_notices SET admin_read_at=? WHERE id=?", (now, nid))
        return 1
    return 0


# -- admin (vod_manager admin session) ----------------------------------------

def admin_requests(status: str | None = None) -> dict:
    sync_active()
    allr = store.rows("SELECT * FROM knm_requests ORDER BY id DESC LIMIT 1000")
    counts: dict[str, int] = {}
    for r in allr:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    shown = [r for r in allr if not status or r["status"] == status]
    return {"requests": [public_view(r, True) for r in shown], "counts": counts}


def _get_request(rid: int) -> dict:
    req = store.one("SELECT * FROM knm_requests WHERE id=?", (rid,))
    if not req:
        raise KnmError(404, "Request not found")
    return req


def retryable_import_jobs(req: dict) -> list[int]:
    """Done downloads whose Radarr/Sonarr import failed or timed out (needs arr_handoff.retry_import)."""
    return [j["id"] for j in _jobs(store.decode_jobs(req)) if j.get("import_status") in ("failed", "timed_out")]


def admin_retry(rid: int) -> dict:
    """Requeues the request's failed/cancelled download jobs. Import retries are done by the route (async)."""
    req = _get_request(rid)
    n = sum(1 for jid in store.decode_jobs(req) if vod_db.retry_download_job(jid))
    if not n and not retryable_import_jobs(req):
        raise KnmError(409, "Nothing to retry for this request")
    _reset(req)
    return sync_request(_get_request(rid))


def _reset(req: dict) -> None:
    """Lets a request that is being retried raise a fresh failed notice if it fails again."""
    store.write("DELETE FROM knm_notices WHERE request_id=? AND kind='failed'", (req["id"],))
    store.write("UPDATE knm_requests SET completed_at=NULL WHERE id=?", (req["id"],))


def admin_cancel(rid: int) -> dict:
    req = _get_request(rid)
    vod_downloader.cancel(store.decode_jobs(req))
    return sync_request(_get_request(rid))


def admin_notices() -> list[dict]:
    sync_active()
    out = []
    for n in store.rows("SELECT * FROM knm_notices WHERE kind='failed' AND admin_read_at IS NULL ORDER BY id DESC"):
        req = store.one("SELECT detail FROM knm_requests WHERE id=?", (n["request_id"],)) or {}
        out.append({"id": n["id"], "request_id": n["request_id"], "title": n["title"], "username": n["username"],
                    "created_at": n["created_at"], "detail": req.get("detail")})
    return out


def admin_clear_notices() -> int:
    """Acknowledges every open failed notice here and the matching vod_manager bell notices."""
    now = time.time()
    n = store.one("SELECT COUNT(*) c FROM knm_notices WHERE kind='failed' AND admin_read_at IS NULL")["c"]
    store.write("UPDATE knm_notices SET admin_read_at=? WHERE kind='failed' AND admin_read_at IS NULL", (now,))
    for b in notices.list_open():
        if b.get("kind") == "knm_download":
            notices.acknowledge(b["id"])
    return n
