"""Startup must not reference names that don't exist, and the language report
stays quick and doesn't leave a stale approval notice behind."""

import ast
import asyncio
import builtins
from pathlib import Path

import main
import notices
import vod_db
import vod_routes


def _module_names(tree: ast.Module) -> set[str]:
    names = set(dir(builtins))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Import):
            names.update((a.asname or a.name).split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.update(a.asname or a.name for a in node.names)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
    return names


def test_every_name_called_in_lifespan_is_defined():
    """A scheduler referenced in lifespan but defined nowhere (a fork-only task)
    crashes the app at boot with a NameError."""
    tree = ast.parse(Path(main.__file__).read_text(encoding="utf-8"))
    known = _module_names(tree)
    lifespan = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "lifespan")
    missing = sorted({
        n.func.id for n in ast.walk(lifespan)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id not in known
    })
    assert not missing, f"lifespan calls undefined names: {missing}"


def test_eligible_totals_are_cached_between_report_loads(db, monkeypatch):
    calls = []
    real = vod_db._language_eligible_counts

    def counting(conn):
        calls.append(1)
        return real(conn)

    monkeypatch.setattr(vod_db, "_language_eligible_counts", counting)
    first = db.language_audit_stats()
    second = db.language_audit_stats()
    assert len(calls) == 1
    assert first["eligible"] == second["eligible"]


def test_report_clears_mismatch_notice_when_nothing_is_pending(db):
    notices.add("language_mismatch", "warn", "Language mismatch approval needed", "x")
    assert db.has_open_notice_kind("language_mismatch")
    report = asyncio.run(vod_routes.language_mismatch_report())
    assert report["count"] == 0
    assert not db.has_open_notice_kind("language_mismatch")
