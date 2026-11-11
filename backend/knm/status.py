# KNM FORK ONLY - NEVER SEND UPSTREAM
"""Maps vod_manager download jobs (plus arr handoff + library presence) to the
person-facing request status. Pure functions, no I/O."""

LABELS = {
    "queued": "Queued",
    "downloading": "Downloading",
    "delayed": "Delayed, retrying",
    "processing": "Downloaded, being prepared",
    "ready": "Ready",
    "failed": "Download failed, an admin has been told",
    "cancelled": "Cancelled",
}
TERMINAL = {"ready", "failed", "cancelled"}

_IMPORT_FAILED = {"needs_manual", "failed", "timed_out"}
# when several episodes are in different states the most active one is shown
_PRECEDENCE = ["downloading", "delayed", "queued", "processing"]


def job_state(job: dict, now: float) -> str:
    st = job.get("status")
    imp = job.get("import_status")
    if st == "cancelled":
        return "cancelled"
    if st == "failed" or imp in _IMPORT_FAILED:
        return "failed"
    if st == "running":
        return "downloading"
    if st == "queued":
        return "delayed" if (job.get("next_try_at") or 0) > now else "queued"
    if st == "done":
        # None = no Radarr/Sonarr handoff configured: nothing further to wait on.
        # 'imported' = Radarr/Sonarr confirmed the file. Anything else is still being prepared.
        return "ready" if imp in (None, "imported") else "processing"
    return "queued"


def derive(jobs: list[dict], in_library: bool, now: float) -> dict:
    """Aggregate status for one request (a movie = 1 job, a show = many)."""
    if not jobs:
        return {"status": "ready" if in_library else "failed", "progress": 1.0 if in_library else 0.0,
                "episodes_total": 0, "episodes_ready": 0,
                "detail": None if in_library else "No download job found for this request"}
    states = [job_state(j, now) for j in jobs]
    if in_library:
        # the media server already has it: that beats any lagging handoff state
        states = ["ready" if s == "processing" else s for s in states]
    live = [s for s in states if s != "cancelled"]
    if not live:
        overall = "cancelled"
    else:
        overall = next((s for s in _PRECEDENCE if s in live), None)
        if overall is None:
            overall = "failed" if "failed" in live else "ready"
    ready = sum(1 for s in states if s == "ready")
    pairs = [(s, j) for s, j in zip(states, jobs) if s != "cancelled"]
    prog = sum(1.0 if s in ("ready", "processing") else float(j.get("progress") or 0.0)
               for s, j in pairs) / max(1, len(pairs))
    detail = "; ".join(
        f"job {j['id']}: {j.get('error') or j.get('import_note') or j.get('import_status') or j.get('status')}"
        for s, j in zip(states, jobs) if s == "failed") or None
    return {"status": overall, "progress": round(prog, 3), "episodes_total": len(jobs),
            "episodes_ready": ready, "detail": detail}
