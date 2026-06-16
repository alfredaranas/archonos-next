"""Gate test for Milestone 4 — Persistent Memory.

The gate (per docs/BASE_PLAN.md M4):
    memory written in session A is recalled in session B after process restart.

Per docs/architecture/CORE_ARCHITECTURE.md §2: memories table has
(id, kind CHECK, body, project, created_at, meta) and a synced FTS5
virtual table (memories_fts). Sync triggers keep the two in lockstep.
Per §4: memory/store.py  remember(conn, kind, body, meta=None) -> int
        memory/recall.py recall(conn, query, k=10) -> list[MemoryHit]
Per §7: gate test IS the definition of done.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from archonos.cli.main import main
from archonos.core import ops
from archonos.memory import ops as mem_ops
from archonos.storage import db


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHONOS_HOME", str(tmp_path))
    ops.init()
    return tmp_path


# --- remember: §4 contract ---


def test_remember_writes_a_memory(isolated_home):
    conn = db.get_connection()
    try:
        mem_id = mem_ops.remember(conn, "note", "hello world")
    finally:
        conn.close()
    assert mem_id > 0
    conn = db.get_connection()
    try:
        row = conn.execute("SELECT kind, body FROM memories WHERE id = ?", (mem_id,)).fetchone()
    finally:
        conn.close()
    assert row["kind"] == "note"
    assert row["body"] == "hello world"


def test_remember_rejects_invalid_kind(isolated_home):
    conn = db.get_connection()
    try:
        with pytest.raises(ValueError):
            mem_ops.remember(conn, "bogus_kind", "x")
    finally:
        conn.close()


def test_remember_accepts_all_spec_kinds(isolated_home):
    conn = db.get_connection()
    try:
        for kind in mem_ops.valid_kinds():
            mem_ops.remember(conn, kind, f"body for {kind}")
    finally:
        conn.close()
    assert mem_ops.count(db.get_connection()) == len(mem_ops.valid_kinds())


def test_remember_populates_memories_fts_via_trigger(isolated_home):
    """The schema has synced FTS5 — a write to memories must appear in memories_fts."""
    conn = db.get_connection()
    try:
        mem_ops.remember(conn, "note", "a distinctive phrase for FTS5 lookup")
        fts_count = int(
            conn.execute("SELECT COUNT(*) AS n FROM memories_fts").fetchone()["n"]
        )
        mem_count = int(
            conn.execute("SELECT COUNT(*) AS n FROM memories").fetchone()["n"]
        )
    finally:
        conn.close()
    assert fts_count == mem_count == 1


# --- recall: §4 contract ---


def test_recall_by_query_finds_written_memory(isolated_home):
    conn = db.get_connection()
    try:
        mem_ops.remember(conn, "decision", "We will use SQLite for local-first storage")
        hits = mem_ops.recall(conn, query="SQLite", limit=10)
    finally:
        conn.close()
    assert len(hits) >= 1
    assert "SQLite" in hits[0].body
    assert 0.0 <= hits[0].rank <= 1.0


def test_recall_with_no_query_returns_recent(isolated_home):
    conn = db.get_connection()
    try:
        mem_ops.remember(conn, "note", "first")
        mem_ops.remember(conn, "note", "second")
        mem_ops.remember(conn, "note", "third")
        hits = mem_ops.recall(conn, query="", limit=10)
    finally:
        conn.close()
    # Most recent first
    assert [h.body for h in hits] == ["third", "second", "first"]


def test_recall_filters_by_kind(isolated_home):
    conn = db.get_connection()
    try:
        mem_ops.remember(conn, "decision", "chose SQLite")
        mem_ops.remember(conn, "note", "SQLite is a database")
        hits = mem_ops.recall(conn, query="SQLite", kind="decision", limit=10)
    finally:
        conn.close()
    assert len(hits) == 1
    assert hits[0].kind == "decision"


def test_recall_no_results_returns_empty(isolated_home):
    conn = db.get_connection()
    try:
        hits = mem_ops.recall(conn, query="xyzzyplugh_nonexistent", limit=5)
    finally:
        conn.close()
    assert hits == []


# --- THE M4 GATE: cross-session persistence ---


def test_gate_m4_memory_persists_across_process_restart(isolated_home):
    """Memory written in 'session A' is recalled in 'session B' after the
    process (i.e. the connection and any in-memory state) has been torn down.

    We simulate a process restart by spawning a fresh Python subprocess
    that runs against the same ARCHONOS_HOME. That subprocess opens its
    own sqlite3.Connection, its own module-level state, its own Python
    interpreter — exactly what would happen if you quit the CLI and
    started it again.
    """
    home = str(isolated_home)

    # --- Session A: write a memory ---
    session_a = subprocess.run(
        [sys.executable, "-c", f"""
import os
os.environ['ARCHONOS_HOME'] = {home!r}
from archonos.memory import ops as mem_ops
from archonos.storage import db
conn = db.get_connection()
try:
    mid = mem_ops.remember(
        conn, 'decision',
        'Selected FTS5 as the search substrate for the knowledge base',
        meta={{'rationale': 'vector search banned post-alpha per spec §8'}}
    )
    print(mid)
finally:
    conn.close()
"""],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert session_a.returncode == 0, (
        f"session A failed: rc={session_a.returncode}\n"
        f"stdout={session_a.stdout}\nstderr={session_a.stderr}"
    )
    written_id = int(session_a.stdout.strip().splitlines()[-1])
    assert written_id > 0

    # --- Session B: new process, recall the memory ---
    session_b = subprocess.run(
        [sys.executable, "-c", f"""
import os, json
os.environ['ARCHONOS_HOME'] = {home!r}
from archonos.memory import ops as mem_ops
from archonos.storage import db
conn = db.get_connection()
try:
    hits = mem_ops.recall(conn, query='FTS5 search substrate', limit=5)
    for h in hits:
        print(json.dumps({{
            'id': h.id, 'kind': h.kind, 'body': h.body,
            'rank': h.rank,
        }}))
finally:
    conn.close()
"""],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert session_b.returncode == 0, (
        f"session B failed: rc={session_b.returncode}\n"
        f"stdout={session_b.stdout}\nstderr={session_b.stderr}"
    )

    hits = [json.loads(line) for line in session_b.stdout.strip().splitlines()]
    assert len(hits) >= 1
    # The exact memory we wrote in session A shows up in session B
    found = next((h for h in hits if h["id"] == written_id), None)
    assert found is not None, (
        f"memory {written_id} not recalled in session B; got: {hits}"
    )
    assert "FTS5" in found["body"]
    assert found["kind"] == "decision"
    assert 0.0 <= found["rank"] <= 1.0


# --- CLI: §5 ---


def test_cli_remember_command(isolated_home):
    assert main(["remember", "we chose SQLite for the kernel"]) == 0


def test_cli_remember_invalid_kind_is_user_error(isolated_home):
    assert main(["remember", "--kind", "bogus", "body"]) == 1


def test_cli_recall_command_finds_memory(isolated_home):
    main(["remember", "SQLite is our database engine"])
    assert main(["recall", "SQLite"]) == 0


def test_cli_recall_with_no_query_returns_recent(isolated_home):
    main(["remember", "first memory"])
    main(["remember", "second memory"])
    assert main(["recall"]) == 0


def test_cli_recall_filters_by_kind(isolated_home):
    main(["remember", "--kind", "decision", "Use SQLite"])
    main(["remember", "--kind", "note", "Some note about Python"])
    assert main(["recall", "--kind", "decision", "SQLite"]) == 0


def test_cli_recall_before_init_is_user_error(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHONOS_HOME", str(tmp_path / "fresh"))
    assert main(["recall", "anything"]) == 1
