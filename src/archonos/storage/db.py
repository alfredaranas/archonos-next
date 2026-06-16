"""Single SQLite connection manager + migration runner.

This module is the ONLY place a connection is opened. Everything else
receives a connection. Swapping SQLite for another backend later means
swapping this factory — not the callers.

Per docs/architecture/CORE_ARCHITECTURE.md §1: one module owns the connection.
Per §2: migrations are numbered SQL files in src/archonos/storage/migrations/.
"""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def archonos_home() -> Path:
    """Root state directory. Override with ARCHONOS_HOME for tests."""
    return Path(os.environ.get("ARCHONOS_HOME", str(Path.home() / ".archonos")))


def project_dir(project: str = "default") -> Path:
    return archonos_home() / project


def db_path(project: str = "default") -> Path:
    return project_dir(project) / "archonos.db"


def get_connection(project: str = "default", create: bool = False) -> sqlite3.Connection:
    """Open the project database. With create=False, the db must already exist."""
    path = db_path(project)
    if not create and not path.exists():
        raise FileNotFoundError(
            f"No database at {path}. Run 'archonos init' first."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def current_schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()
    if row is None:
        return 0
    v = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    return int(v["v"] or 0)


def _migration_files() -> list[tuple[int, Path]]:
    files = []
    for p in sorted(MIGRATIONS_DIR.glob("*.sql")):
        m = re.match(r"^(\d+)_", p.name)
        if m:
            files.append((int(m.group(1)), p))
    return files


def migrate(conn: sqlite3.Connection) -> list[int]:
    """Apply pending numbered migrations. Returns versions applied."""
    applied: list[int] = []
    have = current_schema_version(conn)
    for version, path in _migration_files():
        if version <= have:
            continue
        conn.executescript(path.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO schema_version(version) VALUES (?)", (version,))
        conn.commit()
        applied.append(version)
    return applied
