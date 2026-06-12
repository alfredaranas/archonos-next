"""Gate test for Milestone 5 — Local Alpha.

End-to-end walkthrough proving install → init → import → search → remember → workflow.
This is the consumer experience. If this passes, Local Alpha ships.
"""

from __future__ import annotations
import json
import pytest

from archonos.core import ops
from archonos.knowledge import import_ as kb_import
from archonos.knowledge import search as kb_search
from archonos.memory import ops as mem_ops
from archonos.workflows import ops as wf_ops
from archonos.storage import db


@pytest.fixture(autouse=True)
def fresh_machine(tmp_path, monkeypatch):
    """Simulate a clean machine — empty home, no prior state."""
    monkeypatch.setenv("ARCHONOS_HOME", str(tmp_path))
    return tmp_path


def test_local_alpha_walkthrough(fresh_machine):
    """The full consumer journey, in one test, on a clean machine."""

    # Step 1 — install + init
    init_result = ops.init()
    assert init_result.created
    assert init_result.migrations_applied == [1]

    # Step 2 — healthcheck before any data
    health = ops.healthcheck()
    assert health.ok, [c.detail for c in health.checks if not c.ok]
    check_names = {c.name for c in health.checks}
    assert check_names == {"db_reachable", "schema_version", "write_test", "fts_tables", "disk_space"}

    # Step 3 — status reflects empty state
    s = ops.status()
    assert s.schema_version == 1
    assert (s.documents, s.chunks, s.memories, s.workflows, s.workflow_runs) == (0, 0, 0, 0, 0)

    # Step 4 — import documents
    docs = fresh_machine / "notes"
    docs.mkdir()
    (docs / "lesson1.md").write_text(
        "# SQLite Lessons\n\nFTS5 requires INTEGER rowids. UUID text columns break content_rowid binding."
    )
    (docs / "lesson2.md").write_text(
        "# Architecture\n\nOne connection owner makes the database swappable. Core never prints."
    )
    (docs / "lesson3.md").write_text(
        "# Workflows\n\nA workflow is a JSON spec with typed steps. Sequential only in v1."
    )
    conn = db.get_connection()
    try:
        report = kb_import.import_path(conn, docs)
    finally:
        conn.close()
    assert report.docs_added == 3
    assert report.chunks_added >= 3

    # Step 5 — search returns ranked results
    conn = db.get_connection()
    try:
        hits = kb_search.search(conn, "FTS5 INTEGER rowid")
    finally:
        conn.close()
    assert len(hits) > 0
    assert "FTS5" in hits[0].snippet or "rowid" in hits[0].snippet.lower()

    # Step 6 — remember decisions and lessons
    conn = db.get_connection()
    try:
        mem_ops.remember(conn, "decision", "Adopted SQLite as canonical local store")
        mem_ops.remember(conn, "lesson", "INTEGER PKs everywhere for FTS5 compatibility")
        mem_ops.remember(conn, "note", "Local Alpha gate passed end-to-end")
    finally:
        conn.close()

    # Step 7 — memory survives across "process restart" (new connection)
    conn = db.get_connection()
    try:
        decisions = mem_ops.decisions(conn)
        lessons = mem_ops.lessons(conn)
        assert len(decisions) == 1 and "SQLite" in decisions[0].body
        assert len(lessons) == 1 and "INTEGER" in lessons[0].body
    finally:
        conn.close()

    # Step 8 — register and run a workflow
    spec = {
        "name": "alpha-walkthrough",
        "description": "Three-step end-to-end test workflow",
        "steps": [
            {"name": "ingest", "action": "log", "args": {"message": "starting"}},
            {"name": "process", "action": "log", "args": {"message": "running"}},
            {"name": "report", "action": "log", "args": {"message": "done"}},
        ],
    }
    conn = db.get_connection()
    try:
        wf_id = wf_ops.register(conn, "alpha-walkthrough", spec)
        assert wf_id > 0
        run_id = wf_ops.run_workflow(conn, "alpha-walkthrough")
        runs = wf_ops.list_runs(conn)
        run = next(r for r in runs if r.id == run_id)
        assert run.status == "succeeded"
        log = json.loads(run.log)
        step_names = [e.get("step") for e in log if "step" in e]
        assert "ingest" in step_names
        assert "process" in step_names
        assert "report" in step_names
    finally:
        conn.close()

    # Step 9 — final status reflects everything
    final = ops.status()
    assert final.documents == 3
    assert final.chunks >= 3
    assert final.memories == 3
    assert final.workflows == 1
    assert final.workflow_runs == 1

    # Step 10 — health still green after all activity
    final_health = ops.healthcheck()
    assert final_health.ok


def test_local_alpha_multiple_projects(fresh_machine):
    """Two projects don't leak into each other."""
    ops.init(project="research")
    ops.init(project="trading")

    conn_r = db.get_connection(project="research")
    try:
        mem_ops.remember(conn_r, "decision", "Use Anthropic for analysis", project="research")
    finally:
        conn_r.close()

    conn_t = db.get_connection(project="trading")
    try:
        mem_ops.remember(conn_t, "decision", "Use MiniMax for forecasts", project="trading")
    finally:
        conn_t.close()

    # Each project sees only its own memories
    conn_r = db.get_connection(project="research")
    try:
        r_decisions = mem_ops.decisions(conn_r, project="research")
    finally:
        conn_r.close()
    conn_t = db.get_connection(project="trading")
    try:
        t_decisions = mem_ops.decisions(conn_t, project="trading")
    finally:
        conn_t.close()

    assert len(r_decisions) == 1 and "Anthropic" in r_decisions[0].body
    assert len(t_decisions) == 1 and "MiniMax" in t_decisions[0].body

    # No cross-project leaks
    assert all("MiniMax" not in d.body for d in r_decisions)
    assert all("Anthropic" not in d.body for d in t_decisions)
