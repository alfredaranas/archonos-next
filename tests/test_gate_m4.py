"""Gate test for Milestone 4 — Persistent Memory.

Gate: memory written in one connection is recalled in another (process restart simulation).
"""

from __future__ import annotations

import pytest

from archonos.core import ops
from archonos.memory import ops as mem_ops
from archonos.storage import db


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHONOS_HOME", str(tmp_path))
    ops.init()
    return tmp_path


def fresh_conn():
    """Simulate a new process by opening a fresh connection."""
    return db.get_connection()


def test_remember_returns_id():
    conn = fresh_conn()
    mem_id = mem_ops.remember(conn, "note", "Test memory body")
    conn.close()
    assert isinstance(mem_id, int)


def test_memory_survives_reconnect():
    """Core gate: written in conn A, recalled in conn B."""
    conn_a = fresh_conn()
    mem_ops.remember(conn_a, "decision", "Use SQLite as primary store")
    conn_a.close()

    conn_b = fresh_conn()
    results = mem_ops.recall(conn_b, kind="decision")
    conn_b.close()

    assert len(results) == 1
    assert "SQLite" in results[0].body


def test_recall_by_query():
    conn = fresh_conn()
    mem_ops.remember(conn, "lesson", "FTS5 requires INTEGER rowid not UUID")
    mem_ops.remember(conn, "lesson", "Always use WAL mode for SQLite")
    mem_ops.remember(conn, "note", "Meeting at 3pm")
    conn.close()

    conn2 = fresh_conn()
    results = mem_ops.recall(conn2, query="FTS5 rowid")
    conn2.close()

    assert len(results) >= 1
    assert any("FTS5" in r.body for r in results)


def test_recall_by_kind():
    conn = fresh_conn()
    mem_ops.remember(conn, "decision", "Decision A")
    mem_ops.remember(conn, "decision", "Decision B")
    mem_ops.remember(conn, "lesson", "Lesson A")
    conn.close()

    conn2 = fresh_conn()
    decisions = mem_ops.recall(conn2, kind="decision")
    conn2.close()

    assert len(decisions) == 2
    assert all(d.kind == "decision" for d in decisions)


def test_recall_all():
    conn = fresh_conn()
    for i in range(5):
        mem_ops.remember(conn, "note", f"Note {i}")
    conn.close()

    conn2 = fresh_conn()
    results = mem_ops.recall(conn2)
    conn2.close()

    assert len(results) == 5


def test_recall_limit():
    conn = fresh_conn()
    for i in range(20):
        mem_ops.remember(conn, "note", f"Note {i} with some content to search")
    conn.close()

    conn2 = fresh_conn()
    results = mem_ops.recall(conn2, limit=5)
    conn2.close()

    assert len(results) == 5


def test_decisions_helper():
    conn = fresh_conn()
    mem_ops.remember(conn, "decision", "Use integer PKs")
    mem_ops.remember(conn, "lesson", "Not a decision")
    conn.close()

    conn2 = fresh_conn()
    decisions = mem_ops.decisions(conn2)
    conn2.close()

    assert all(d.kind == "decision" for d in decisions)
    assert any("integer" in d.body.lower() for d in decisions)


def test_lessons_helper():
    conn = fresh_conn()
    mem_ops.remember(conn, "lesson", "FTS5 is fast")
    mem_ops.remember(conn, "decision", "Not a lesson")
    conn.close()

    conn2 = fresh_conn()
    lessons = mem_ops.lessons(conn2)
    conn2.close()

    assert all(l.kind == "lesson" for l in lessons)


def test_memory_kinds_valid():
    conn = fresh_conn()
    for kind in ("decision", "state", "lesson", "note", "workflow_outcome"):
        mem_ops.remember(conn, kind, f"Body for {kind}")
    conn.close()

    conn2 = fresh_conn()
    all_mem = mem_ops.recall(conn2)
    conn2.close()
    assert len(all_mem) == 5


def test_status_reflects_memories():
    conn = fresh_conn()
    mem_ops.remember(conn, "note", "A memory")
    mem_ops.remember(conn, "decision", "A decision")
    conn.close()

    s = ops.status()
    assert s.memories == 2
