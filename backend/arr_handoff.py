"""Library handoff: gets finished downloads into Radarr/Sonarr (and so into Plex).

1. When a download is queued, the title is looked up in Radarr/Sonarr and added if
   missing (never searching). Jobs go import_status add -> ready | needs_manual.
2. When the file appears in the "finished" folder (after an encoder such as Tdarr),
   the watcher asks Radarr/Sonarr to import it and confirms the import.
Off until Radarr/Sonarr are configured (config.handoff_enabled)."""

import asyncio
import logging

import config
import vod_db
from arr_client import ArrClient, ArrError

logger = logging.getLogger(__name__)

_APP = {"movie": "radarr", "episode": "sonarr"}
MANUAL_NOTE = "Add this title to Radarr/Sonarr manually"


def client_for(kind: str) -> ArrClient | None:
    """Radarr client for movie jobs, Sonarr for episode jobs; None when not configured."""
    app = _APP[kind]
    url, key = config.get_handoff_settings()[f"{app}_url"], config.get_handoff_api_key(app)
    return ArrClient(app, url, key) if url and key else None


def _title_for(job: dict) -> tuple[tuple, int | None, str, int | None]:
    """(group key, tmdb id, title, year) of the movie or series the job belongs to."""
    if job["kind"] == "movie":
        row = vod_db.get_movie(job["item_id"])
        key = ("movie", job["item_id"])
    else:
        episode = vod_db.get_episode(job["item_id"])
        row = vod_db.get_series(episode["series_id"]) if episode else None
        key = ("series", episode["series_id"] if episode else None)
    if not row:
        return key, None, "", None
    tmdb = row.get("tmdb_id")
    return key, int(tmdb) if tmdb and str(tmdb).isdigit() else None, row["name"], row.get("year")


def _resolve_group(client, kind: str, tmdb: int | None, title: str, year: int | None) -> tuple[str, int | None, str | None]:
    """(import_status, arr_id, note) for one movie/series."""
    try:
        item = client.lookup(tmdb, title, year)
        if item is None:
            return "needs_manual", None, MANUAL_NOTE
        if not item.get("id"):
            s = config.get_handoff_settings()
            app = _APP[kind]
            monitor = s["new_movie_monitor"] if kind == "movie" else s["new_show_monitor"]
            item = client.add(item, s[f"{app}_root"], s[f"{app}_profile_id"], monitor)
            logger.info("[handoff] added %r to %s (monitor=%s, no search)", title, app, monitor)
        return "ready", int(item["id"]), None
    except ArrError as exc:
        return "add", None, str(exc)                # stays 'add': retried on the next tick


def _resolve_pending_sync() -> None:
    groups: dict[tuple, list[dict]] = {}
    meta: dict[tuple, tuple] = {}
    for job in vod_db.list_import_jobs(("add",)):
        key, tmdb, title, year = _title_for(job)
        groups.setdefault(key, []).append(job)
        meta[key] = (job["kind"], tmdb, title, year)
    for key, jobs in groups.items():
        kind, tmdb, title, year = meta[key]
        client = client_for(kind)
        if client is None:
            continue
        status, arr_id, note = _resolve_group(client, kind, tmdb, title, year) if title else \
            ("needs_manual", None, MANUAL_NOTE)
        for job in jobs:
            vod_db.update_import(job["id"], import_status=status, arr_id=arr_id, import_note=note)


async def resolve_pending() -> None:
    """Looks up / adds the titles of every 'add' job, one call per movie or series."""
    await asyncio.to_thread(_resolve_pending_sync)
