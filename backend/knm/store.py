# KNM FORK ONLY - NEVER SEND UPSTREAM
"""KNM's own tables, created here (no change to vod_manager's schema code)."""

import json
import time

import vod_db

DEFAULT_CAP = 5

_SCHEMA = """
CREATE TABLE IF NOT EXISTS knm_allowlist (
    server_id  INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    username   TEXT,
    allowed    INTEGER NOT NULL DEFAULT 1,
    daily_cap  INTEGER,
    updated_at REAL NOT NULL,
    PRIMARY KEY (server_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_knm_allowlist_username ON knm_allowlist(lower(trim(username)));
CREATE TABLE IF NOT EXISTS knm_settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS knm_requests (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id    INTEGER NOT NULL,
    user_id      INTEGER NOT NULL,
    username     TEXT,
    kind         TEXT NOT NULL,
    title        TEXT NOT NULL,
    year         INTEGER,
    tmdb_id      TEXT,
    item_kind    TEXT NOT NULL,
    item_id      INTEGER NOT NULL,
    job_ids      TEXT NOT NULL DEFAULT '[]',
    status       TEXT NOT NULL,
    detail       TEXT,
    progress     REAL NOT NULL DEFAULT 0,
    episodes_total INTEGER NOT NULL DEFAULT 0,
    episodes_ready INTEGER NOT NULL DEFAULT 0,
    created_at   REAL NOT NULL,
    updated_at   REAL NOT NULL,
    completed_at REAL
);
CREATE INDEX IF NOT EXISTS idx_knm_requests_user ON knm_requests(server_id, user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_knm_requests_username ON knm_requests(lower(trim(username)), created_at);
CREATE TABLE IF NOT EXISTS knm_notices (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL,
    server_id  INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    username   TEXT,
    kind       TEXT NOT NULL,
    title      TEXT NOT NULL,
    req_kind   TEXT,
    tmdb_id    TEXT,
    created_at REAL NOT NULL,
    read_at    REAL,
    admin_read_at REAL,
    UNIQUE (request_id, kind)
);
"""

_ensured: set = set()


def ensure_schema() -> None:
    key = str(vod_db.DB_PATH)
    if key in _ensured:
        return
    with vod_db._WRITE_LOCK:
        conn = vod_db._connect()
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()
    _ensured.add(key)


def write(sql: str, params=(), rowcount: bool = False) -> int:
    """One write statement under vod_manager's write lock; returns lastrowid (or rowcount)."""
    ensure_schema()
    with vod_db._WRITE_LOCK:
        conn = vod_db._connect()
        try:
            cur = conn.execute(sql, params)
            vod_db._commit_with_retry(conn)
            return cur.rowcount if rowcount else cur.lastrowid
        finally:
            conn.close()


def rows(sql: str, params=()) -> list[dict]:
    ensure_schema()
    conn = vod_db._connect()
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def one(sql: str, params=()) -> dict | None:
    r = rows(sql, params)
    return r[0] if r else None


# -- settings / allow-list ---------------------------------------------------

def default_cap() -> int:
    r = one("SELECT value FROM knm_settings WHERE key='default_cap'")
    return int(r["value"]) if r and str(r["value"]).isdigit() else DEFAULT_CAP


def set_default_cap(cap: int) -> None:
    write("INSERT INTO knm_settings (key, value) VALUES ('default_cap', ?) "
          "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(int(cap)),))


def name_key(username: str | None) -> str:
    """Identity key for allow/deny and caps: lowercased, trimmed username ('' if unknown)."""
    return (username or "").strip().lower()


def get_entry(server_id: int, user_id: int) -> dict | None:
    return one("SELECT * FROM knm_allowlist WHERE server_id=? AND user_id=?", (server_id, user_id))


def find_by_username(username: str | None) -> dict | None:
    """Effective allow-list entry for a username across ALL servers (None if no rows).

    Rows for the same username on several servers (legacy data) are combined:
      * allowed  = True if ANY row is allowed;
      * daily_cap = the cap of the MOST RECENTLY UPDATED allowed row (NULL = use default cap);
        if no row is allowed, the most recently updated row's values are returned.
    """
    key = name_key(username)
    if not key:
        return None
    matches = rows("SELECT * FROM knm_allowlist WHERE lower(trim(username))=? "
                   "ORDER BY updated_at DESC, rowid DESC", (key,))
    if not matches:
        return None
    allowed = [m for m in matches if m["allowed"]]
    best = dict(allowed[0] if allowed else matches[0])
    best["allowed"] = bool(allowed)
    return best


def upsert_entry(server_id: int, user_id: int, username: str | None, allowed: bool, daily_cap: int | None) -> None:
    """Upsert BY USERNAME: every existing row for that (case-insensitive, trimmed) username is updated, so
    one entry covers all servers; if none exists a row is inserted keyed (server_id, user_id) for audit.
    Without a username it falls back to the (server_id, user_id) key."""
    now = time.time()
    key = name_key(username)
    if key:
        n = write("UPDATE knm_allowlist SET username=?, allowed=?, daily_cap=?, updated_at=? "
                  "WHERE lower(trim(username))=?", (username.strip(), 1 if allowed else 0, daily_cap, now, key),
                  rowcount=True)
        if n:
            return
    write("INSERT INTO knm_allowlist (server_id, user_id, username, allowed, daily_cap, updated_at) "
          "VALUES (?,?,?,?,?,?) ON CONFLICT(server_id, user_id) DO UPDATE SET "
          "username=COALESCE(excluded.username, username), allowed=excluded.allowed, "
          "daily_cap=excluded.daily_cap, updated_at=excluded.updated_at",
          (server_id, user_id, username.strip() if username else None, 1 if allowed else 0, daily_cap, now))


def delete_entry(server_id: int, user_id: int) -> bool:
    ensure_schema()
    with vod_db._WRITE_LOCK:
        conn = vod_db._connect()
        try:
            n = conn.execute("DELETE FROM knm_allowlist WHERE server_id=? AND user_id=?", (server_id, user_id)).rowcount
            vod_db._commit_with_retry(conn)
            return n > 0
        finally:
            conn.close()


def list_entries() -> list[dict]:
    out = rows("SELECT * FROM knm_allowlist ORDER BY server_id, user_id")
    for e in out:
        e["allowed"] = bool(e["allowed"])
    return out


# -- requests -----------------------------------------------------------------

def day_start(now: float | None = None) -> float:
    now = time.time() if now is None else now
    return now - (now % 86400)          # UTC midnight


def used_today(server_id: int, user_id: int, now: float | None = None, username: str | None = None) -> int:
    """Titles requested since UTC midnight. Counted by username (all servers) when known,
    else by (server_id, user_id)."""
    key = name_key(username)
    if key:
        return one("SELECT COUNT(*) c FROM knm_requests WHERE lower(trim(username))=? AND created_at>=?",
                   (key, day_start(now)))["c"]
    return one("SELECT COUNT(*) c FROM knm_requests WHERE server_id=? AND user_id=? AND created_at>=?",
               (server_id, user_id, day_start(now)))["c"]


def decode_jobs(req: dict) -> list[int]:
    try:
        return [int(x) for x in json.loads(req.get("job_ids") or "[]")]
    except (ValueError, TypeError):
        return []
