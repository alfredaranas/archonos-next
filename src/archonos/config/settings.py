"""Local settings helpers for ArchonOS.

Per docs/architecture/CORE_ARCHITECTURE.md §4: get/set over settings table;
ARCHONOS_HOME env override.
"""

from __future__ import annotations

import os
from pathlib import Path

APP_DIR = ".archonos"
DB_NAME = "archonos.db"


def project_root(path: str | Path | None = None) -> Path:
    """Return the project root used for local ArchonOS state."""
    return Path(path or Path.cwd()).resolve()


def archonos_home() -> Path:
    """Return the ArchonOS state root (env override: ARCHONOS_HOME)."""
    return Path(os.environ.get("ARCHONOS_HOME", str(Path.home() / APP_DIR)))


def app_dir(path: str | Path | None = None) -> Path:
    """Return the .archonos directory for a project."""
    return project_root(path) / APP_DIR


def database_path(path: str | Path | None = None) -> Path:
    """Return the SQLite database path for a project."""
    return app_dir(path) / DB_NAME
