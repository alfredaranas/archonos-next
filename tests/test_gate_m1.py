"""Gate test for Milestone 1 — CLI kernel.

The gate: init/status/healthcheck all exit 0 on a fresh home; init is idempotent.
Schema must match docs/architecture/CORE_ARCHITECTURE.md §2 (verbatim).

Per CORE_ARCHITECTURE.md §7: every module contract gets a unit test against
a tmp-path SQLite db; gate tests are runnable individually; gate test
defines done.
"""

from __future__ import annotations

import pytest

from archonos.cli.main import main
from archonos.core import ops


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHONOS_HOME", str(tmp_path))
    return tmp_path


def test_init_creates_db(isolated_home):
    r = ops.init()
    assert r.created
    assert (isolated_home / "default" / "archonos.db").exists()
    assert r.migrations_applied == [1]


def test_init_idempotent():
    ops.init()
    r2 = ops.init()
    assert not r2.created
    assert r2.migrations_applied == []


def test_status_counts_zero_on_fresh_project():
    ops.init()
    s = ops.status()
    assert s.schema_version == 1
    assert (s.documents, s.chunks, s.memories, s.workflows, s.workflow_runs) == (0, 0, 0, 0, 0)


def test_status_fails_before_init():
    with pytest.raises(FileNotFoundError):
        ops.status()


def test_healthcheck_all_green_after_init():
    ops.init()
    h = ops.healthcheck()
    assert h.ok, [f"{c.name}: {c.detail}" for c in h.checks if not c.ok]
    assert {c.name for c in h.checks} == {
        "db_reachable", "schema_version", "write_test", "fts_tables", "disk_space",
    }


def test_cli_exit_codes():
    assert main(["init"]) == 0
    assert main(["status"]) == 0
    assert main(["healthcheck"]) == 0


def test_cli_status_before_init_is_user_error(isolated_home, monkeypatch):
    monkeypatch.setenv("ARCHONOS_HOME", str(isolated_home / "fresh"))
    assert main(["status"]) == 1


# --- Schema-shape guards: enforce the frozen DDL ---
# If anyone edits the migration in a way that violates §2, these fail.

def test_schema_has_required_tables():
    from archonos.storage import db
    ops.init()
    conn = db.get_connection()
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table') ORDER BY name"
        ).fetchall()
        names = {r["name"] for r in rows}
        assert {"documents", "chunks", "memories", "workflows",
                "workflow_runs", "settings", "schema_version"}.issubset(names)
    finally:
        conn.close()


def test_schema_has_fts5_virtual_tables():
    from archonos.storage import db
    ops.init()
    conn = db.get_connection()
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_fts'"
        ).fetchall()
        names = {r["name"] for r in rows}
        assert {"chunks_fts", "memories_fts"}.issubset(names)
    finally:
        conn.close()


def test_documents_columns_match_spec():
    from archonos.storage import db
    ops.init()
    conn = db.get_connection()
    try:
        rows = conn.execute("PRAGMA table_info(documents)").fetchall()
        cols = {r["name"]: r for r in rows}
        # Spec §2: id, source_path, title, doc_type, sha256, byte_size, imported_at, meta
        for col in ("id", "source_path", "title", "doc_type", "sha256", "byte_size", "imported_at", "meta"):
            assert col in cols, f"documents missing column: {col}"
        # INTEGER PK — never TEXT (FTS5 lesson)
        assert cols["id"]["type"].upper() == "INTEGER", "documents.id must be INTEGER (FTS5 content_rowid)"
        # sha256 must be UNIQUE for dedupe — SQLite auto-index names don't contain "sha256",
        # so check that there's a unique index covering the sha256 column
        idx = conn.execute("PRAGMA index_list(documents)").fetchall()
        sha256_unique = False
        for i in idx:
            cols = conn.execute(f"PRAGMA index_info({i['name']})").fetchall()
            col_names = {c["name"] for c in cols}
            if col_names == {"sha256"}:
                sha256_unique = True
                break
        assert sha256_unique, "documents.sha256 needs a UNIQUE index"
    finally:
        conn.close()


def test_chunks_foreign_key_cascade():
    from archonos.storage import db
    ops.init()
    conn = db.get_connection()
    try:
        rows = conn.execute("PRAGMA foreign_key_list(chunks)").fetchall()
        fks = [r for r in rows if r["table"] == "documents"]
        assert len(fks) == 1, "chunks must FK -> documents"
        assert fks[0]["on_delete"].upper() == "CASCADE", "FK must be ON DELETE CASCADE"
    finally:
        conn.close()


def test_memories_kind_has_check_constraint():
    from archonos.storage import db
    ops.init()
    conn = db.get_connection()
    try:
        # Insert with a valid kind — should succeed
        conn.execute(
            "INSERT INTO memories(kind, body) VALUES (?, ?)",
            ("note", "test"),
        )
        # Insert with an invalid kind — should fail (CHECK constraint)
        with pytest.raises(Exception):
            conn.execute(
                "INSERT INTO memories(kind, body) VALUES (?, ?)",
                ("bogus_kind", "test"),
            )
    finally:
        conn.close()
