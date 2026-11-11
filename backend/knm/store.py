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


def write(sql: str, params=()) -> int:
    """One write statement under vod_manager's write lock; returns lastrowid."""
    ensure_schema()
    with vod_db._WRITE_LOCK:
        conn = vod_db._connect()
        try:
            cur = conn.execute(sql, params)
            vod_db._commit_with_retry(conn)
            return cur.lastrowid
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


def get_entry(server_id: int, user_id: int) -> dict | None:
    return one("SELECT * FROM knm_allowlist WHERE server_id=? AND user_id=?", (server_id, user_id))


def upsert_entry(server_id: int, user_id: int, username: str | None, allowed: bool, daily_cap: int | None) -> None:
    write("INSERT INTO knm_allowlist (server_id, user_id, username, allowed, daily_cap, updated_at) "
          "VALUES (?,?,?,?,?,?) ON CONFLICT(server_id, user_id) DO UPDATE SET "
          "username=COALESCE(excluded.username, username), allowed=excluded.allowed, "
          "daily_cap=excluded.daily_cap, updated_at=excluded.updated_at",
          (server_id, user_id, username, 1 if allowed else 0, daily_cap, time.time()))


def list_entries() -> list[dict]:
    out = rows("SELECT * FROM knm_allowlist ORDER BY server_id, user_id")
    for e in out:
        e["allowed"] = bool(e["allowed"])
    return out


# -- requests -----------------------------------------------------------------

def day_start(now: float | None = None) -> float:
    now = time.time() if now is None else now
    return now - (now % 86400)          # UTC midnight


def used_today(server_id: int, user_id: int, now: float | None = None) -> int:
    return one("SELECT COUNT(*) c FROM knm_requests WHERE server_id=? AND user_id=? AND created_at>=?",
               (server_id, user_id, day_start(now)))["c"]


def decode_jobs(req: dict) -> list[int]:
    try:
        return [int(x) for x in json.loads(req.get("job_ids") or "[]")]
    except (ValueError, TypeError):
        return []
