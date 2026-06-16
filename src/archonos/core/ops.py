"""Core operations: init, status, healthcheck.

Pure functions returning dataclasses. No printing — the CLI formats.

Per docs/architecture/CORE_ARCHITECTURE.md §1: core never prints.
"""

from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass, field

from archonos.storage import db


@dataclass
class InitResult:
    project: str
    db_path: str
    created: bool
    migrations_applied: list[int] = field(default_factory=list)


@dataclass
class StatusResult:
    project: str
    db_path: str
    schema_version: int
    documents: int
    chunks: int
    memories: int
    workflows: int
    workflow_runs: int


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


@dataclass
class HealthResult:
    checks: list[Check]

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)


def init(project: str = "default") -> InitResult:
    """Create project dir + db, apply migrations. Idempotent."""
    existed = db.db_path(project).exists()
    conn = db.get_connection(project, create=True)
    try:
        applied = db.migrate(conn)
        conn.execute(
            "INSERT OR REPLACE INTO settings(key, value) VALUES ('project', ?)",
            (project,),
        )
        conn.commit()
    finally:
        conn.close()
    return InitResult(
        project=project,
        db_path=str(db.db_path(project)),
        created=not existed,
        migrations_applied=applied,
    )


def status(project: str = "default") -> StatusResult:
    conn = db.get_connection(project)
    try:
        def count(table: str) -> int:
            return int(conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"])

        return StatusResult(
            project=project,
            db_path=str(db.db_path(project)),
            schema_version=db.current_schema_version(conn),
            documents=count("documents"),
            chunks=count("chunks"),
            memories=count("memories"),
            workflows=count("workflows"),
            workflow_runs=count("workflow_runs"),
        )
    finally:
        conn.close()


def healthcheck(project: str = "default") -> HealthResult:
    checks: list[Check] = []

    # 1. db reachable
    try:
        conn = db.get_connection(project)
        checks.append(Check("db_reachable", True, str(db.db_path(project))))
    except FileNotFoundError as e:
        checks.append(Check("db_reachable", False, str(e)))
        return HealthResult(checks)

    try:
        # 2. schema current
        have = db.current_schema_version(conn)
        want = max((v for v, _ in db._migration_files()), default=0)
        checks.append(
            Check("schema_version", have == want, f"have v{have}, latest v{want}")
        )

        # 3. write test
        try:
            conn.execute(
                "INSERT OR REPLACE INTO settings(key, value) VALUES ('_healthcheck', datetime('now'))"
            )
            conn.commit()
            checks.append(Check("write_test", True, "settings write ok"))
        except sqlite3.Error as e:
            checks.append(Check("write_test", False, str(e)))

        # 4. fts present
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM sqlite_master WHERE name IN ('chunks_fts','memories_fts')"
        ).fetchone()
        checks.append(Check("fts_tables", int(row["n"]) == 2, f"{row['n']}/2 fts tables"))

        # 5. disk space (>100MB free)
        free = shutil.disk_usage(db.project_dir(project)).free
        checks.append(
            Check("disk_space", free > 100 * 1024 * 1024, f"{free // (1024*1024)}MB free")
        )
    finally:
        conn.close()

    return HealthResult(checks)
