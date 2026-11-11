# KNM FORK ONLY - NEVER SEND UPSTREAM
"""Status mapping: download job + arr handoff + library presence -> the person-facing status."""

import pytest

from knm import status

NOW = 1000.0


def job(**kw):
    base = {"id": 1, "status": "queued", "next_try_at": 0, "note": None, "error": None,
            "import_status": None, "import_note": None, "progress": 0.0}
    base.update(kw)
    return base


@pytest.mark.parametrize("j,expected", [
    (job(), "queued"),
    (job(status="running", progress=0.4), "downloading"),
    (job(status="queued", next_try_at=NOW + 60, note="Provider said HTTP 429. Trying again in 5 min"), "delayed"),
    (job(status="queued", next_try_at=NOW - 1, note="old note"), "queued"),
    (job(status="done", import_status="add"), "processing"),
    (job(status="done", import_status="waiting"), "processing"),
    (job(status="done", import_status="importing"), "processing"),
    (job(status="done", import_status="ready"), "processing"),
    (job(status="done", import_status="imported"), "ready"),
    (job(status="done", import_status=None), "ready"),
    (job(status="failed", error="boom"), "failed"),
    (job(status="done", import_status="needs_manual"), "failed"),
    (job(status="done", import_status="failed"), "failed"),
    (job(status="done", import_status="timed_out"), "failed"),
    (job(status="cancelled"), "cancelled"),
])
def test_single_job_mapping(j, expected):
    assert status.derive([j], in_library=False, now=NOW)["status"] == expected


def test_library_presence_is_ready_fallback():
    out = status.derive([job(status="done", import_status="waiting")], in_library=True, now=NOW)
    assert out["status"] == "ready"


def test_no_jobs_in_library_is_ready():
    assert status.derive([], in_library=True, now=NOW)["status"] == "ready"


def test_no_jobs_not_in_library_is_failed():
    assert status.derive([], in_library=False, now=NOW)["status"] == "failed"


def test_show_active_beats_terminal():
    jobs = [job(id=1, status="done", import_status="imported"), job(id=2, status="running"),
            job(id=3, status="queued")]
    out = status.derive(jobs, in_library=False, now=NOW)
    assert out["status"] == "downloading"
    assert out["episodes_total"] == 3 and out["episodes_ready"] == 1


def test_show_failed_only_when_nothing_active():
    jobs = [job(id=1, status="failed"), job(id=2, status="running")]
    assert status.derive(jobs, in_library=False, now=NOW)["status"] == "downloading"
    jobs = [job(id=1, status="failed"), job(id=2, status="done", import_status="imported")]
    assert status.derive(jobs, in_library=False, now=NOW)["status"] == "failed"


def test_show_all_ready():
    jobs = [job(id=i, status="done", import_status="imported") for i in range(3)]
    out = status.derive(jobs, in_library=False, now=NOW)
    assert out["status"] == "ready" and out["episodes_ready"] == 3


def test_progress_is_average():
    jobs = [job(id=1, status="running", progress=0.5), job(id=2, status="queued")]
    assert status.derive(jobs, in_library=False, now=NOW)["progress"] == 0.25


def test_failure_detail_is_technical_but_label_is_plain():
    out = status.derive([job(status="failed", error="HTTP 503 from prov")], in_library=False, now=NOW)
    assert "503" in out["detail"]
    assert status.LABELS["failed"] == "Download failed, an admin has been told"
